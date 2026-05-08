use aes::Aes256;
use base64::{
    alphabet,
    engine::{
        general_purpose::{self, GeneralPurpose, GeneralPurposeConfig},
        Engine as _,
    },
};
use cbc::cipher::{block_padding::Pkcs7, BlockDecryptMut, KeyIvInit};
use quick_xml::{events::Event, Reader};
use serde_json::{json, Value};
use sha1::{Digest, Sha1};
use std::{error::Error, fmt};

type Aes256CbcDec = cbc::Decryptor<Aes256>;
const WECOM_BASE64: GeneralPurpose = GeneralPurpose::new(
    &alphabet::STANDARD,
    GeneralPurposeConfig::new().with_decode_allow_trailing_bits(true),
);

#[derive(Clone, Debug)]
pub struct WecomCrypto {
    token: String,
    corp_id: String,
    aes_key: Vec<u8>,
}

#[derive(Debug, Eq, PartialEq)]
pub enum WecomCryptoError {
    InvalidKeyLength,
    InvalidAesKey,
    InvalidSignature,
    InvalidXml,
    MissingEncrypt,
    InvalidBase64,
    CiphertextTooShort,
    DecryptFailed,
    PlaintextTooShort,
    InvalidMessageLength,
    CorpIdMismatch { got: String, want: String },
}

impl fmt::Display for WecomCryptoError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::InvalidKeyLength => write!(f, "encodingAESKey must be 43 characters"),
            Self::InvalidAesKey => write!(f, "decode AES key"),
            Self::InvalidSignature => write!(f, "signature verification failed"),
            Self::InvalidXml => write!(f, "parse encrypted message"),
            Self::MissingEncrypt => write!(f, "encrypted message is missing Encrypt"),
            Self::InvalidBase64 => write!(f, "base64 decode"),
            Self::CiphertextTooShort => write!(f, "ciphertext too short"),
            Self::DecryptFailed => write!(f, "decrypt message"),
            Self::PlaintextTooShort => write!(f, "plaintext too short"),
            Self::InvalidMessageLength => write!(f, "invalid message length"),
            Self::CorpIdMismatch { got, want } => {
                write!(f, "corpID mismatch: got {got}, want {want}")
            }
        }
    }
}

impl Error for WecomCryptoError {}

impl WecomCrypto {
    pub fn new(
        token: impl Into<String>,
        encoding_aes_key: &str,
        corp_id: impl Into<String>,
    ) -> Result<Self, WecomCryptoError> {
        if encoding_aes_key.len() != 43 {
            return Err(WecomCryptoError::InvalidKeyLength);
        }

        let aes_key = decode_encoding_aes_key(encoding_aes_key)?;
        if aes_key.len() != 32 {
            return Err(WecomCryptoError::InvalidAesKey);
        }

        Ok(Self {
            token: token.into(),
            corp_id: corp_id.into(),
            aes_key,
        })
    }

    pub fn verify_url(
        &self,
        msg_signature: &str,
        timestamp: &str,
        nonce: &str,
        echo_str: &str,
    ) -> Result<String, WecomCryptoError> {
        if !self.verify_signature(msg_signature, timestamp, nonce, echo_str) {
            return Err(WecomCryptoError::InvalidSignature);
        }

        self.decrypt(echo_str)
    }

    pub fn decrypt_msg(
        &self,
        msg_signature: &str,
        timestamp: &str,
        nonce: &str,
        post_data: &[u8],
    ) -> Result<Vec<u8>, WecomCryptoError> {
        let encrypted = extract_xml_text(post_data, b"Encrypt")?;
        if !self.verify_signature(msg_signature, timestamp, nonce, &encrypted) {
            return Err(WecomCryptoError::InvalidSignature);
        }

        self.decrypt(&encrypted).map(String::into_bytes)
    }

    pub fn verify_signature(
        &self,
        msg_signature: &str,
        timestamp: &str,
        nonce: &str,
        encrypted: &str,
    ) -> bool {
        self.generate_signature(timestamp, nonce, encrypted) == msg_signature
    }

    pub fn generate_signature(&self, timestamp: &str, nonce: &str, encrypted: &str) -> String {
        let mut values = [self.token.as_str(), timestamp, nonce, encrypted];
        values.sort_unstable();
        let joined = values.join("");
        hex::encode(Sha1::digest(joined.as_bytes()))
    }

    pub fn decrypt(&self, encrypted: &str) -> Result<String, WecomCryptoError> {
        let cipher_text = general_purpose::STANDARD
            .decode(encrypted)
            .map_err(|_| WecomCryptoError::InvalidBase64)?;
        if cipher_text.len() < 16 {
            return Err(WecomCryptoError::CiphertextTooShort);
        }

        let mut plain = cipher_text;
        let plain = Aes256CbcDec::new_from_slices(&self.aes_key, &self.aes_key[..16])
            .map_err(|_| WecomCryptoError::InvalidAesKey)?
            .decrypt_padded_mut::<Pkcs7>(&mut plain)
            .map_err(|_| WecomCryptoError::DecryptFailed)?;

        if plain.len() < 20 {
            return Err(WecomCryptoError::PlaintextTooShort);
        }

        let msg_len = u32::from_be_bytes([plain[16], plain[17], plain[18], plain[19]]) as usize;
        if plain.len() < 20 + msg_len {
            return Err(WecomCryptoError::InvalidMessageLength);
        }

        let msg = &plain[20..20 + msg_len];
        let corp_id = String::from_utf8_lossy(&plain[20 + msg_len..]).to_string();
        if corp_id != self.corp_id {
            return Err(WecomCryptoError::CorpIdMismatch {
                got: corp_id,
                want: self.corp_id.clone(),
            });
        }

        Ok(String::from_utf8_lossy(msg).to_string())
    }
}

pub fn decode_encoding_aes_key(encoding_aes_key: &str) -> Result<Vec<u8>, WecomCryptoError> {
    WECOM_BASE64
        .decode(format!("{encoding_aes_key}="))
        .map_err(|_| WecomCryptoError::InvalidAesKey)
}

#[derive(Debug, Default, Eq, PartialEq)]
pub struct ReceivedMessage {
    pub from_user_name: String,
    pub msg_type: String,
    pub msg_id: String,
    pub content: String,
    pub recognition: String,
    pub title: String,
    pub description: String,
    pub event: String,
    pub event_key: String,
    pub response_code: String,
    pub task_id: String,
    pub card_type: String,
}

#[derive(Clone, Debug, PartialEq)]
pub struct WecomTemplateAction {
    pub action_id: String,
    pub value: Value,
}

pub fn parse_received_message(xml: &[u8]) -> Result<ReceivedMessage, WecomCryptoError> {
    let mut reader = Reader::from_reader(xml);
    reader.config_mut().trim_text(true);
    let mut current_tag = Vec::new();
    let mut message = ReceivedMessage::default();

    loop {
        match reader.read_event() {
            Ok(Event::Start(event)) => {
                current_tag = event.name().as_ref().to_vec();
            }
            Ok(Event::Text(event)) => {
                apply_received_message_text(
                    &mut message,
                    &current_tag,
                    String::from_utf8_lossy(event.as_ref()).as_ref(),
                );
            }
            Ok(Event::CData(event)) => {
                apply_received_message_text(
                    &mut message,
                    &current_tag,
                    String::from_utf8_lossy(event.as_ref()).as_ref(),
                );
            }
            Ok(Event::End(_)) => {
                current_tag.clear();
            }
            Ok(Event::Eof) => break,
            Err(_) => return Err(WecomCryptoError::InvalidXml),
            _ => {}
        }
    }

    Ok(message)
}

pub fn parse_message_content(message: &ReceivedMessage) -> String {
    match message.msg_type.as_str() {
        "text" => message.content.clone(),
        "voice" if !message.recognition.is_empty() => message.recognition.clone(),
        "voice" => "[语音消息]".to_string(),
        "image" => "[图片消息]".to_string(),
        "video" => "[视频消息]".to_string(),
        "location" => "[位置消息]".to_string(),
        "link" => format!("{} {}", message.title, message.description),
        _ => String::new(),
    }
}

pub fn parse_template_action(event_key: &str) -> Option<WecomTemplateAction> {
    let event_key = event_key.trim();
    if event_key.is_empty() {
        return None;
    }

    let Some((action_id, raw_value)) = event_key.split_once(':') else {
        return Some(WecomTemplateAction {
            action_id: event_key.to_string(),
            value: json!({}),
        });
    };

    let value = match serde_json::from_str::<Value>(raw_value) {
        Ok(Value::Object(object)) => Value::Object(object),
        Ok(value) => json!({ "value": value }),
        Err(_) => json!({}),
    };

    Some(WecomTemplateAction {
        action_id: action_id.to_string(),
        value,
    })
}

fn apply_received_message_text(message: &mut ReceivedMessage, tag: &[u8], text: &str) {
    match tag {
        b"FromUserName" => message.from_user_name = text.to_string(),
        b"MsgType" => message.msg_type = text.to_string(),
        b"MsgId" => message.msg_id = text.to_string(),
        b"Content" => message.content = text.to_string(),
        b"Recognition" => message.recognition = text.to_string(),
        b"Title" => message.title = text.to_string(),
        b"Description" => message.description = text.to_string(),
        b"Event" => message.event = text.to_string(),
        b"EventKey" => message.event_key = text.to_string(),
        b"ResponseCode" => message.response_code = text.to_string(),
        b"TaskId" => message.task_id = text.to_string(),
        b"CardType" => message.card_type = text.to_string(),
        _ => {}
    }
}

fn extract_xml_text(xml: &[u8], tag: &[u8]) -> Result<String, WecomCryptoError> {
    let mut reader = Reader::from_reader(xml);
    reader.config_mut().trim_text(true);
    let mut inside_tag = false;

    loop {
        match reader.read_event() {
            Ok(Event::Start(event)) if event.name().as_ref() == tag => {
                inside_tag = true;
            }
            Ok(Event::Text(event)) if inside_tag => {
                return Ok(String::from_utf8_lossy(event.as_ref()).to_string());
            }
            Ok(Event::CData(event)) if inside_tag => {
                return Ok(String::from_utf8_lossy(event.as_ref()).to_string());
            }
            Ok(Event::End(event)) if event.name().as_ref() == tag => {
                return Err(WecomCryptoError::MissingEncrypt);
            }
            Ok(Event::Eof) => break,
            Err(_) => return Err(WecomCryptoError::InvalidXml),
            _ => {}
        }
    }

    Err(WecomCryptoError::MissingEncrypt)
}

#[cfg(test)]
mod tests {
    use super::{
        parse_message_content, parse_received_message, parse_template_action, WecomCrypto,
        WecomCryptoError,
    };
    use aes::Aes256;
    use base64::{engine::general_purpose, Engine as _};
    use cbc::cipher::{block_padding::Pkcs7, BlockEncryptMut, KeyIvInit};
    use std::{
        sync::atomic::{AtomicU64, Ordering},
        time::{SystemTime, UNIX_EPOCH},
    };

    type Aes256CbcEnc = cbc::Encryptor<Aes256>;

    const TOKEN: &str = "test-token";
    const KEY: &str = "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG";
    const CORP_ID: &str = "corp123";

    #[test]
    fn validates_key_length_and_decoded_size() {
        let crypt = WecomCrypto::new(TOKEN, KEY, CORP_ID).unwrap();
        assert_eq!(crypt.aes_key.len(), 32);

        assert_eq!(
            WecomCrypto::new(TOKEN, "too-short", CORP_ID).unwrap_err(),
            WecomCryptoError::InvalidKeyLength
        );
    }

    #[test]
    fn generates_and_verifies_signature() {
        let crypt = WecomCrypto::new(TOKEN, KEY, CORP_ID).unwrap();
        let nonce = test_nonce();
        let signature = crypt.generate_signature("1704067200", &nonce, "encrypted-data");

        assert!(crypt.verify_signature(&signature, "1704067200", &nonce, "encrypted-data"));
        assert!(!crypt.verify_signature("invalid-sig", "1704067200", &nonce, "encrypted-data"));
    }

    #[test]
    fn decrypts_round_trip_payload() {
        let crypt = WecomCrypto::new(TOKEN, KEY, CORP_ID).unwrap();
        let encrypted = encrypt_for_test("Hello, WeChat!", &crypt.aes_key, CORP_ID);

        let decrypted = crypt.decrypt(&encrypted).unwrap();

        assert_eq!(decrypted, "Hello, WeChat!");
    }

    #[test]
    fn verifies_url_and_returns_decrypted_echo() {
        let crypt = WecomCrypto::new(TOKEN, KEY, CORP_ID).unwrap();
        let encrypted = encrypt_for_test("echo-ok", &crypt.aes_key, CORP_ID);
        let nonce = test_nonce();
        let signature = crypt.generate_signature("1704067200", &nonce, &encrypted);

        let echo = crypt
            .verify_url(&signature, "1704067200", &nonce, &encrypted)
            .unwrap();

        assert_eq!(echo, "echo-ok");
    }

    #[test]
    fn decrypts_encrypted_xml_message() {
        let crypt = WecomCrypto::new(TOKEN, KEY, CORP_ID).unwrap();
        let plain =
            "<xml><MsgType><![CDATA[text]]></MsgType><Content><![CDATA[hello]]></Content></xml>";
        let encrypted = encrypt_for_test(plain, &crypt.aes_key, CORP_ID);
        let nonce = test_nonce();
        let signature = crypt.generate_signature("1704067200", &nonce, &encrypted);
        let xml = format!(
            "<xml><ToUserName><![CDATA[{CORP_ID}]]></ToUserName><Encrypt><![CDATA[{encrypted}]]></Encrypt><AgentID>1</AgentID></xml>"
        );

        let decrypted = crypt
            .decrypt_msg(&signature, "1704067200", &nonce, xml.as_bytes())
            .unwrap();

        assert_eq!(decrypted, plain.as_bytes());
    }

    #[test]
    fn parses_received_message_content_like_gateway_contract() {
        let text = parse_received_message(
            br#"<xml><FromUserName><![CDATA[user1]]></FromUserName><MsgType><![CDATA[text]]></MsgType><Content><![CDATA[/confirm req_1]]></Content><MsgId>42</MsgId></xml>"#,
        )
        .unwrap();
        assert_eq!(text.from_user_name, "user1");
        assert_eq!(text.msg_type, "text");
        assert_eq!(text.msg_id, "42");
        assert_eq!(parse_message_content(&text), "/confirm req_1");

        let voice = parse_received_message(
            r#"<xml><MsgType><![CDATA[voice]]></MsgType><Recognition><![CDATA[查看需求]]></Recognition></xml>"#
                .as_bytes(),
        )
        .unwrap();
        assert_eq!(parse_message_content(&voice), "查看需求");

        let link = parse_received_message(
            br#"<xml><MsgType><![CDATA[link]]></MsgType><Title><![CDATA[T]]></Title><Description><![CDATA[D]]></Description></xml>"#,
        )
        .unwrap();
        assert_eq!(parse_message_content(&link), "T D");
    }

    #[test]
    fn parses_template_card_event_fields_and_action_payload() {
        let message = parse_received_message(
            br#"<xml><FromUserName><![CDATA[user1]]></FromUserName><MsgType><![CDATA[event]]></MsgType><Event><![CDATA[template_card_event]]></Event><EventKey><![CDATA[confirm:{"req_id":"req_1"}]]></EventKey><ResponseCode><![CDATA[resp_1]]></ResponseCode><TaskId><![CDATA[task_1]]></TaskId><CardType><![CDATA[button_interaction]]></CardType></xml>"#,
        )
        .unwrap();

        assert_eq!(message.event, "template_card_event");
        assert_eq!(message.event_key, r#"confirm:{"req_id":"req_1"}"#);
        assert_eq!(message.response_code, "resp_1");
        assert_eq!(message.task_id, "task_1");
        assert_eq!(message.card_type, "button_interaction");

        let action = parse_template_action(&message.event_key).unwrap();
        assert_eq!(action.action_id, "confirm");
        assert_eq!(action.value["req_id"], "req_1");
    }

    #[test]
    fn parses_template_action_like_python_adapter() {
        let simple = parse_template_action("confirm_requirement").unwrap();
        assert_eq!(simple.action_id, "confirm_requirement");
        assert_eq!(simple.value, serde_json::json!({}));

        let invalid = parse_template_action("confirm:not_valid_json").unwrap();
        assert_eq!(invalid.action_id, "confirm");
        assert_eq!(invalid.value, serde_json::json!({}));

        let scalar = parse_template_action(r#"confirm:"just_a_string""#).unwrap();
        assert_eq!(scalar.action_id, "confirm");
        assert_eq!(scalar.value, serde_json::json!({"value": "just_a_string"}));

        assert!(parse_template_action("").is_none());
    }

    #[test]
    fn rejects_invalid_inputs() {
        let crypt = WecomCrypto::new(TOKEN, KEY, CORP_ID).unwrap();

        assert_eq!(
            crypt.decrypt("not-valid-base64").unwrap_err(),
            WecomCryptoError::InvalidBase64
        );
        assert_eq!(
            crypt
                .decrypt(&general_purpose::STANDARD.encode(b"short"))
                .unwrap_err(),
            WecomCryptoError::CiphertextTooShort
        );
        assert_eq!(
            crypt
                .decrypt_msg("invalid", "1704067200", &test_nonce(), b"not xml")
                .unwrap_err(),
            WecomCryptoError::MissingEncrypt
        );
    }

    #[test]
    fn rejects_corp_id_mismatch() {
        let crypt = WecomCrypto::new(TOKEN, KEY, CORP_ID).unwrap();
        let encrypted = encrypt_for_test("hello", &crypt.aes_key, "wrong-corp");

        assert_eq!(
            crypt.decrypt(&encrypted).unwrap_err(),
            WecomCryptoError::CorpIdMismatch {
                got: "wrong-corp".to_string(),
                want: CORP_ID.to_string()
            }
        );
    }

    fn encrypt_for_test(plain_text: &str, aes_key: &[u8], corp_id: &str) -> String {
        let mut plain = Vec::new();
        plain.extend_from_slice(&test_random_prefix());
        plain.extend_from_slice(&(plain_text.len() as u32).to_be_bytes());
        plain.extend_from_slice(plain_text.as_bytes());
        plain.extend_from_slice(corp_id.as_bytes());

        let msg_len = plain.len();
        plain.resize(msg_len + 16, 0);

        let cipher_text = Aes256CbcEnc::new_from_slices(aes_key, &aes_key[..16])
            .unwrap()
            .encrypt_padded_mut::<Pkcs7>(&mut plain, msg_len)
            .unwrap();

        general_purpose::STANDARD.encode(cipher_text)
    }

    fn test_nonce() -> String {
        static NONCE_COUNTER: AtomicU64 = AtomicU64::new(1);
        let nanos = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let counter = NONCE_COUNTER.fetch_add(1, Ordering::Relaxed);
        format!("{nanos:x}{counter:x}")
    }

    fn test_random_prefix() -> [u8; 16] {
        SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos()
            .to_be_bytes()
    }
}
