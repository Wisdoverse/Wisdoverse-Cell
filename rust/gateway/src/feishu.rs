use aes::Aes256;
use base64::{engine::general_purpose, Engine as _};
use cbc::cipher::{block_padding::NoPadding, BlockDecryptMut, KeyIvInit};
use serde::Deserialize;
use sha2::{Digest, Sha256};
use std::{error::Error, fmt};
use subtle::ConstantTimeEq;

type Aes256CbcDec = cbc::Decryptor<Aes256>;

#[derive(Debug, Eq, PartialEq)]
pub enum FeishuCryptoError {
    MissingEncryptKey,
    InvalidBase64,
    PayloadTooShort,
    InvalidBlockSize,
    DecryptFailed,
    MissingJson,
}

impl fmt::Display for FeishuCryptoError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::MissingEncryptKey => write!(f, "encrypt key is required"),
            Self::InvalidBase64 => write!(f, "decode encrypted payload"),
            Self::PayloadTooShort => write!(f, "encrypted payload is too short"),
            Self::InvalidBlockSize => write!(f, "encrypted payload block size is invalid"),
            Self::DecryptFailed => write!(f, "decrypt encrypted payload"),
            Self::MissingJson => write!(f, "decrypted payload does not contain JSON"),
        }
    }
}

impl Error for FeishuCryptoError {}

pub fn verify_signature(
    timestamp: &str,
    nonce: &str,
    encrypt_key: &str,
    body: &[u8],
    signature: &str,
) -> bool {
    if encrypt_key.is_empty() {
        return false;
    }

    let mut hasher = Sha256::new();
    hasher.update(timestamp.as_bytes());
    hasher.update(nonce.as_bytes());
    hasher.update(encrypt_key.as_bytes());
    hasher.update(body);
    let expected = hex::encode(hasher.finalize());

    expected.as_bytes().ct_eq(signature.as_bytes()).into()
}

pub fn decrypt_message(encrypted: &str, encrypt_key: &str) -> Result<Vec<u8>, FeishuCryptoError> {
    if encrypt_key.is_empty() {
        return Err(FeishuCryptoError::MissingEncryptKey);
    }

    let cipher_text = general_purpose::STANDARD
        .decode(encrypted)
        .map_err(|_| FeishuCryptoError::InvalidBase64)?;

    if cipher_text.len() < 16 {
        return Err(FeishuCryptoError::PayloadTooShort);
    }

    let (iv, payload) = cipher_text.split_at(16);
    if payload.len() % 16 != 0 {
        return Err(FeishuCryptoError::InvalidBlockSize);
    }

    let key = Sha256::digest(encrypt_key.as_bytes());
    let mut plain = payload.to_vec();
    let plain = Aes256CbcDec::new(&key, iv.into())
        .decrypt_padded_mut::<NoPadding>(&mut plain)
        .map_err(|_| FeishuCryptoError::DecryptFailed)?;

    let start = plain
        .iter()
        .position(|byte| *byte == b'{')
        .ok_or(FeishuCryptoError::MissingJson)?;
    let end = plain
        .iter()
        .rposition(|byte| *byte == b'}')
        .filter(|end| *end >= start)
        .ok_or(FeishuCryptoError::MissingJson)?;

    Ok(plain[start..=end].to_vec())
}

#[derive(Debug, Deserialize)]
pub struct MessageEvent {
    pub sender: Sender,
    pub message: Message,
}

#[derive(Debug, Deserialize)]
pub struct Sender {
    pub sender_id: SenderId,
}

#[derive(Debug, Deserialize)]
pub struct SenderId {
    #[serde(default)]
    pub open_id: String,
}

#[derive(Debug, Deserialize)]
pub struct Message {
    pub message_id: String,
    pub chat_id: String,
    pub message_type: String,
    pub content: String,
}

#[derive(Debug, Deserialize)]
struct TextContent {
    #[serde(default)]
    text: String,
}

pub fn parse_message_content(message_type: &str, content: &str) -> String {
    match message_type {
        "text" => serde_json::from_str::<TextContent>(content)
            .map(|content| content.text)
            .unwrap_or_else(|_| content.to_string()),
        "post" => parse_post_content(content),
        "image" => "[图片]".to_string(),
        "file" => "[文件]".to_string(),
        "audio" => "[语音]".to_string(),
        "video" => "[视频]".to_string(),
        other => format!("[{other}]"),
    }
}

fn parse_post_content(content: &str) -> String {
    let Ok(post) = serde_json::from_str::<serde_json::Value>(content) else {
        return content.to_string();
    };

    let mut text = Vec::new();
    if let Some(title) = post.get("title").and_then(|value| value.as_str()) {
        if !title.is_empty() {
            text.push(title.to_string());
        }
    }
    if let Some(paragraphs) = post.get("content").and_then(|value| value.as_array()) {
        for paragraph in paragraphs {
            let Some(elements) = paragraph.as_array() else {
                continue;
            };
            for element in elements {
                let tag = element.get("tag").and_then(|value| value.as_str());
                if !matches!(tag, Some("text" | "a")) {
                    continue;
                }
                if let Some(value) = element.get("text").and_then(|value| value.as_str()) {
                    if !value.is_empty() {
                        text.push(value.to_string());
                    }
                }
            }
        }
    }

    text.join(" ")
}

#[cfg(test)]
mod tests {
    use super::{decrypt_message, parse_message_content, verify_signature, FeishuCryptoError};
    use aes::Aes256;
    use base64::{engine::general_purpose, Engine as _};
    use cbc::cipher::{block_padding::NoPadding, BlockEncryptMut, KeyIvInit};
    use sha2::{Digest, Sha256};

    type Aes256CbcEnc = cbc::Encryptor<Aes256>;

    #[test]
    fn verifies_valid_signature() {
        let timestamp = "1704067200";
        let nonce = "abc123";
        let encrypt_key = "test-encrypt-key";
        let body = br#"{"event":"test"}"#;
        let signature = signature_for(timestamp, nonce, encrypt_key, body);

        assert!(verify_signature(
            timestamp,
            nonce,
            encrypt_key,
            body,
            &signature
        ));
    }

    #[test]
    fn rejects_invalid_signature_inputs() {
        let timestamp = "1704067200";
        let nonce = "abc123";
        let encrypt_key = "test-encrypt-key";
        let body = br#"{"event":"test"}"#;
        let signature = signature_for(timestamp, nonce, encrypt_key, body);

        assert!(!verify_signature(
            "1704067201",
            nonce,
            encrypt_key,
            body,
            &signature
        ));
        assert!(!verify_signature(
            timestamp,
            nonce,
            "",
            body,
            "any-signature"
        ));
        assert!(!verify_signature(
            timestamp,
            nonce,
            encrypt_key,
            br#"{"event":"modified"}"#,
            &signature
        ));
    }

    #[test]
    fn decrypts_encrypted_payload() {
        let input = r#"{"test":"data"}"#;
        let encrypted = encrypt_for_test(input, "test-encrypt-key");

        let decrypted = decrypt_message(&encrypted, "test-encrypt-key").unwrap();

        assert_eq!(decrypted, input.as_bytes());
    }

    #[test]
    fn rejects_invalid_encrypted_payloads() {
        assert_eq!(
            decrypt_message("payload", "").unwrap_err(),
            FeishuCryptoError::MissingEncryptKey
        );
        assert_eq!(
            decrypt_message("not-base64", "key").unwrap_err(),
            FeishuCryptoError::InvalidBase64
        );
        assert_eq!(
            decrypt_message(&general_purpose::STANDARD.encode(b"short"), "key").unwrap_err(),
            FeishuCryptoError::PayloadTooShort
        );
        assert_eq!(
            decrypt_message(&encrypt_for_test("not-json", "key"), "key").unwrap_err(),
            FeishuCryptoError::MissingJson
        );
    }

    #[test]
    fn parses_message_content_like_gateway_contract() {
        assert_eq!(
            parse_message_content("text", r#"{"text":"/confirm req_123"}"#),
            "/confirm req_123"
        );
        assert_eq!(
            parse_message_content(
                "post",
                r#"{"title":"PRD","content":[[{"tag":"text","text":"hello"},{"tag":"a","text":"link"}]]}"#
            ),
            "PRD hello link"
        );
        assert_eq!(parse_message_content("image", "{}"), "[图片]");
        assert_eq!(parse_message_content("unknown", "{}"), "[unknown]");
    }

    fn signature_for(timestamp: &str, nonce: &str, encrypt_key: &str, body: &[u8]) -> String {
        let mut hasher = Sha256::new();
        hasher.update(timestamp.as_bytes());
        hasher.update(nonce.as_bytes());
        hasher.update(encrypt_key.as_bytes());
        hasher.update(body);
        hex::encode(hasher.finalize())
    }

    fn encrypt_for_test(plain_text: &str, encrypt_key: &str) -> String {
        let key = Sha256::digest(encrypt_key.as_bytes());
        let iv = b"1234567890abcdef";
        let mut padded = plain_text.as_bytes().to_vec();
        let padding = 16 - padded.len() % 16;
        padded.extend(std::iter::repeat_n(padding as u8, padding));

        let msg_len = padded.len();
        let cipher_text = Aes256CbcEnc::new(&key, iv.into())
            .encrypt_padded_mut::<NoPadding>(&mut padded, msg_len)
            .unwrap();

        let mut payload = iv.to_vec();
        payload.extend_from_slice(cipher_text);
        general_purpose::STANDARD.encode(payload)
    }
}
