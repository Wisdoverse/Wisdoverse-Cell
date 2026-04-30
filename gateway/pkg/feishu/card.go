package feishu

// Card represents a Feishu interactive card.
type Card struct {
	Config   *CardConfig   `json:"config,omitempty"`
	Header   *CardHeader   `json:"header,omitempty"`
	Elements []interface{} `json:"elements,omitempty"`
}

// CardConfig configures card behavior.
type CardConfig struct {
	WideScreenMode bool `json:"wide_screen_mode,omitempty"`
	EnableForward  bool `json:"enable_forward,omitempty"`
}

// CardHeader is the card header.
type CardHeader struct {
	Title    *CardText `json:"title,omitempty"`
	Subtitle *CardText `json:"subtitle,omitempty"`
	Template string    `json:"template,omitempty"` // blue, green, orange, red, etc.
}

// CardText represents text content.
type CardText struct {
	Tag     string `json:"tag"`               // plain_text or lark_md
	Content string `json:"content"`
}

// CardDivider is a horizontal divider.
type CardDivider struct {
	Tag string `json:"tag"` // hr
}

// CardMarkdown is markdown content.
type CardMarkdown struct {
	Tag     string `json:"tag"` // markdown
	Content string `json:"content"`
}

// CardDiv is a content block.
type CardDiv struct {
	Tag    string      `json:"tag"` // div
	Text   *CardText   `json:"text,omitempty"`
	Fields []CardField `json:"fields,omitempty"`
}

// CardField is a field in a div.
type CardField struct {
	IsShort bool      `json:"is_short"`
	Text    *CardText `json:"text"`
}

// CardActionBlock is an action block containing buttons.
type CardActionBlock struct {
	Tag     string       `json:"tag"` // action
	Actions []CardButton `json:"actions"`
	Layout  string       `json:"layout,omitempty"` // bisected, trisection, flow
}

// CardButton is an action button.
type CardButton struct {
	Tag   string                 `json:"tag"` // button
	Text  *CardText              `json:"text"`
	Type  string                 `json:"type,omitempty"`  // default, primary, danger
	Value map[string]interface{} `json:"value,omitempty"` // Custom callback data
	URL   string                 `json:"url,omitempty"`
}

// CardNote is a note section.
type CardNote struct {
	Tag      string    `json:"tag"` // note
	Elements []CardText `json:"elements"`
}

// NewDivider creates a horizontal divider.
func NewDivider() *CardDivider {
	return &CardDivider{Tag: "hr"}
}

// NewMarkdown creates a markdown block.
func NewMarkdown(content string) *CardMarkdown {
	return &CardMarkdown{
		Tag:     "markdown",
		Content: content,
	}
}

// NewButton creates an action button.
func NewButton(text, btnType string, value map[string]interface{}) *CardButton {
	return &CardButton{
		Tag:   "button",
		Text:  &CardText{Tag: "plain_text", Content: text},
		Type:  btnType,
		Value: value,
	}
}

// NewPrimaryButton creates a primary (blue) button.
func NewPrimaryButton(text string, value map[string]interface{}) *CardButton {
	return NewButton(text, "primary", value)
}

// NewDangerButton creates a danger (red) button.
func NewDangerButton(text string, value map[string]interface{}) *CardButton {
	return NewButton(text, "danger", value)
}

// NewDefaultButton creates a default (gray) button.
func NewDefaultButton(text string, value map[string]interface{}) *CardButton {
	return NewButton(text, "default", value)
}

// CardBuilder helps build cards fluently.
type CardBuilder struct {
	card *Card
}

// NewCardBuilder creates a new card builder.
func NewCardBuilder() *CardBuilder {
	return &CardBuilder{
		card: &Card{
			Config: &CardConfig{
				WideScreenMode: true,
				EnableForward:  true,
			},
			Elements: make([]interface{}, 0),
		},
	}
}

// SetHeader sets the card header.
func (b *CardBuilder) SetHeader(title, template string) *CardBuilder {
	b.card.Header = &CardHeader{
		Title:    &CardText{Tag: "plain_text", Content: title},
		Template: template,
	}
	return b
}

// SetHeaderWithSubtitle sets the card header with a subtitle.
func (b *CardBuilder) SetHeaderWithSubtitle(title, subtitle, template string) *CardBuilder {
	b.card.Header = &CardHeader{
		Title:    &CardText{Tag: "plain_text", Content: title},
		Subtitle: &CardText{Tag: "plain_text", Content: subtitle},
		Template: template,
	}
	return b
}

// AddMarkdown adds a markdown block.
func (b *CardBuilder) AddMarkdown(content string) *CardBuilder {
	b.card.Elements = append(b.card.Elements, NewMarkdown(content))
	return b
}

// AddDivider adds a horizontal divider.
func (b *CardBuilder) AddDivider() *CardBuilder {
	b.card.Elements = append(b.card.Elements, NewDivider())
	return b
}

// AddActions adds an action block with buttons.
func (b *CardBuilder) AddActions(buttons ...*CardButton) *CardBuilder {
	actions := make([]CardButton, len(buttons))
	for i, btn := range buttons {
		actions[i] = *btn
	}
	b.card.Elements = append(b.card.Elements, &CardActionBlock{
		Tag:     "action",
		Actions: actions,
	})
	return b
}

// AddNote adds a note section.
func (b *CardBuilder) AddNote(text string) *CardBuilder {
	b.card.Elements = append(b.card.Elements, &CardNote{
		Tag: "note",
		Elements: []CardText{
			{Tag: "plain_text", Content: text},
		},
	})
	return b
}

// Build returns the built card.
func (b *CardBuilder) Build() *Card {
	return b.card
}
