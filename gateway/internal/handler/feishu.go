package handler

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"

	"github.com/Wisdoverse/project-cell/gateway/internal/client"
	"github.com/Wisdoverse/project-cell/gateway/internal/config"
	"github.com/Wisdoverse/project-cell/gateway/internal/service"
	"github.com/Wisdoverse/project-cell/gateway/pkg/feishu"
	"github.com/gin-gonic/gin"
	"go.uber.org/zap"
)

// FeishuHandler handles Feishu webhook callbacks.
type FeishuHandler struct {
	cfg           *config.FeishuConfig
	reqClient     *client.RequirementClient
	matcher       *service.Matcher
	sessionMgr    *service.SessionManager
	dedup         *service.Deduplicator
	feishuClient  *feishu.Client
	chatAgentAddr string
	pmAgentAddr   string
	internalKey   string
	httpClient    *http.Client
	logger        *zap.Logger
}

// NewFeishuHandler creates a new Feishu webhook handler.
func NewFeishuHandler(
	cfg *config.FeishuConfig,
	reqClient *client.RequirementClient,
	matcher *service.Matcher,
	sessionMgr *service.SessionManager,
	dedup *service.Deduplicator,
	chatAgentAddr string,
	pmAgentAddr string,
	logger *zap.Logger,
) *FeishuHandler {
	return &FeishuHandler{
		cfg:           cfg,
		reqClient:     reqClient,
		matcher:       matcher,
		sessionMgr:    sessionMgr,
		dedup:         dedup,
		feishuClient:  feishu.NewClient(cfg.AppID, cfg.AppSecret),
		chatAgentAddr: chatAgentAddr,
		pmAgentAddr:   pmAgentAddr,
		internalKey:   cfg.InternalServiceKey,
		httpClient:    &http.Client{Timeout: 30 * time.Second},
		logger:        logger,
	}
}

// Webhook handles POST /api/feishu/webhook
func (h *FeishuHandler) Webhook(c *gin.Context) {
	// Read body
	body, err := io.ReadAll(c.Request.Body)
	if err != nil {
		h.logger.Error("failed to read body", zap.Error(err))
		c.JSON(http.StatusBadRequest, gin.H{"code": -1, "msg": "invalid body"})
		return
	}

	// Verify signature if enabled
	if h.cfg.VerifySignature {
		if h.cfg.EncryptKey == "" {
			h.logger.Error("feishu signature verification is enabled without encrypt_key")
			c.JSON(http.StatusServiceUnavailable, gin.H{"code": -1, "msg": "signature verification is not configured"})
			return
		}
		timestamp := c.GetHeader("X-Lark-Request-Timestamp")
		nonce := c.GetHeader("X-Lark-Request-Nonce")
		signature := c.GetHeader("X-Lark-Signature")

		if !feishu.VerifySignature(timestamp, nonce, h.cfg.EncryptKey, body, signature) {
			h.logger.Warn("invalid signature")
			c.JSON(http.StatusUnauthorized, gin.H{"code": -1, "msg": "invalid signature"})
			return
		}
	}

	// Parse request
	var req feishu.WebhookRequest
	if err := json.Unmarshal(body, &req); err != nil {
		h.logger.Error("failed to parse request", zap.Error(err))
		c.JSON(http.StatusBadRequest, gin.H{"code": -1, "msg": "invalid json"})
		return
	}

	// Store raw body for potential forwarding
	c.Set("rawBody", body)

	// Handle different request types
	// Feishu v2.0 events have no "type" field but have "header"
	if req.Type == "" && req.Header != nil {
		req.Type = feishu.EventTypeCallback
	}

	switch req.Type {
	case feishu.EventTypeURLVerification:
		h.handleURLVerification(c, &req)

	case feishu.EventTypeCallback:
		h.handleEventCallback(c, &req)

	case feishu.EventTypeCardAction:
		h.handleCardAction(c, &req)

	default:
		// Check if it's a card action without type field
		if len(req.Action) > 0 {
			h.handleCardAction(c, &req)
			return
		}
		h.logger.Warn("unknown request type", zap.String("type", req.Type))
		c.JSON(http.StatusOK, gin.H{"code": 0})
	}
}

// handleURLVerification handles the URL verification challenge.
func (h *FeishuHandler) handleURLVerification(c *gin.Context, req *feishu.WebhookRequest) {
	h.logger.Info("url verification")
	c.JSON(http.StatusOK, gin.H{"challenge": req.Challenge})
}

// handleEventCallback handles event subscription callbacks.
func (h *FeishuHandler) handleEventCallback(c *gin.Context, req *feishu.WebhookRequest) {
	if req.Header == nil {
		c.JSON(http.StatusOK, gin.H{"code": 0})
		return
	}

	eventType := req.Header.EventType
	h.logger.Info("event callback", zap.String("event_type", eventType))

	switch eventType {
	case feishu.MessageReceiveV1:
		h.handleMessageEvent(c, req)
	case feishu.CardActionTrigger:
		h.handleCardActionTrigger(c, req)
	default:
		h.logger.Debug("unhandled event type", zap.String("event_type", eventType))
		c.JSON(http.StatusOK, gin.H{"code": 0})
	}
}

// handleMessageEvent handles incoming message events.
func (h *FeishuHandler) handleMessageEvent(c *gin.Context, req *feishu.WebhookRequest) {
	var event feishu.MessageEvent
	if err := json.Unmarshal(req.Event, &event); err != nil {
		h.logger.Error("failed to parse message event", zap.Error(err))
		c.JSON(http.StatusOK, gin.H{"code": 0})
		return
	}

	msg := event.Message
	ctx := c.Request.Context()

	// Check for duplicate message
	if h.dedup != nil {
		isDup, err := h.dedup.IsDuplicate(ctx, msg.MessageID)
		if err != nil {
			h.logger.Warn("dedup check failed", zap.Error(err))
		} else if isDup {
			h.logger.Debug("duplicate message ignored", zap.String("message_id", msg.MessageID))
			c.JSON(http.StatusOK, gin.H{"code": 0})
			return
		}
	}

	h.logger.Info("message received",
		zap.String("message_id", msg.MessageID),
		zap.String("chat_id", msg.ChatID),
		zap.String("message_type", msg.MessageType),
	)

	// Parse message content
	content := feishu.ParseMessageContent(msg.MessageType, msg.Content)

	// Record message in session history
	if h.sessionMgr != nil {
		userID := event.Sender.SenderID.OpenID
		if err := h.sessionMgr.AddMessage(ctx, msg.ChatID, userID, "user", content); err != nil {
			h.logger.Warn("failed to record message", zap.Error(err))
		}
	}

	// Try to match a skill
	match := h.matcher.Match(content)
	if match != nil {
		h.logger.Info("skill matched",
			zap.String("skill", match.SkillName),
			zap.String("match_type", match.MatchType),
			zap.Any("params", match.Parameters),
		)

		// Execute skill via gRPC
		h.executeSkill(c, match, &event)
		return
	}

	// No skill matched - forward to chat-agent
	h.logger.Info("no skill matched, forwarding to chat-agent", zap.String("content", content))
	h.forwardToChatAgent(c)
}

// executeSkill executes a matched skill via gRPC.
func (h *FeishuHandler) executeSkill(c *gin.Context, match *service.SkillMatch, event *feishu.MessageEvent) {
	ctx := c.Request.Context()
	chatID := event.Message.ChatID
	messageID := event.Message.MessageID

	switch match.SkillName {
	case "list":
		// Get page from params or default to 1
		page := 1
		if p, ok := match.Parameters["page"]; ok {
			if pInt, err := parseInt(p); err == nil {
				page = pInt
			}
		}

		// List pending requirements
		resp, err := h.reqClient.ListRequirements(ctx, "PENDING", int32(page), 5)
		if err != nil {
			h.logger.Error("list requirements failed", zap.Error(err))
			c.JSON(http.StatusOK, gin.H{"code": 0})
			return
		}

		h.logger.Info("list requirements success",
			zap.Int("count", len(resp.Requirements)),
			zap.Int32("total", resp.Total),
		)

		// Convert to template requirements
		requirements := make([]feishu.Requirement, len(resp.Requirements))
		for i, r := range resp.Requirements {
			requirements[i] = feishu.Requirement{
				ID:          r.Id,
				Title:       r.Title,
				Description: r.Description,
				Status:      r.Status,
				Priority:    r.Priority,
				Category:    r.Category,
			}
		}

		// Build and send card
		card := feishu.BuildRequirementsListCard(requirements, page, int(resp.TotalPages), int(resp.Total))
		if err := h.feishuClient.SendCard(ctx, "chat_id", chatID, card); err != nil {
			h.logger.Error("send card failed", zap.Error(err))
		}

		c.JSON(http.StatusOK, gin.H{"code": 0})

	case "confirm":
		reqID := match.Parameters["requirement_id"]
		if reqID == "" {
			h.logger.Warn("confirm missing requirement_id")
			c.JSON(http.StatusOK, gin.H{"code": 0})
			return
		}

		userID := event.Sender.SenderID.OpenID
		resp, err := h.reqClient.ConfirmRequirement(ctx, reqID, userID)

		var card *feishu.Card
		if err != nil {
			h.logger.Error("confirm requirement failed", zap.Error(err))
			card = feishu.BuildOperationResultCard("confirm", false, nil, err.Error())
		} else if !resp.Success {
			card = feishu.BuildOperationResultCard("confirm", false, nil, resp.Error)
		} else {
			req := &feishu.Requirement{
				ID:    resp.Requirement.Id,
				Title: resp.Requirement.Title,
			}
			card = feishu.BuildOperationResultCard("confirm", true, req, "")
		}

		if err := h.feishuClient.ReplyCard(ctx, messageID, card); err != nil {
			h.logger.Error("send card failed", zap.Error(err))
		}

		h.logger.Info("confirm requirement",
			zap.String("requirement_id", reqID),
			zap.Bool("success", resp != nil && resp.Success),
		)

		c.JSON(http.StatusOK, gin.H{"code": 0})

	case "reject":
		reqID := match.Parameters["requirement_id"]
		reason := match.Parameters["reason"]
		if reqID == "" {
			h.logger.Warn("reject missing requirement_id")
			c.JSON(http.StatusOK, gin.H{"code": 0})
			return
		}

		userID := event.Sender.SenderID.OpenID
		resp, err := h.reqClient.RejectRequirement(ctx, reqID, reason, userID)

		var card *feishu.Card
		if err != nil {
			h.logger.Error("reject requirement failed", zap.Error(err))
			card = feishu.BuildOperationResultCard("reject", false, nil, err.Error())
		} else if !resp.Success {
			card = feishu.BuildOperationResultCard("reject", false, nil, resp.Error)
		} else {
			req := &feishu.Requirement{
				ID:    resp.Requirement.Id,
				Title: resp.Requirement.Title,
			}
			card = feishu.BuildOperationResultCard("reject", true, req, "")
		}

		if err := h.feishuClient.ReplyCard(ctx, messageID, card); err != nil {
			h.logger.Error("send card failed", zap.Error(err))
		}

		h.logger.Info("reject requirement",
			zap.String("requirement_id", reqID),
			zap.Bool("success", resp != nil && resp.Success),
		)

		c.JSON(http.StatusOK, gin.H{"code": 0})

	case "help":
		card := feishu.BuildHelpCard()
		if err := h.feishuClient.ReplyCard(ctx, messageID, card); err != nil {
			h.logger.Error("send help card failed", zap.Error(err))
		}
		h.logger.Info("help requested")
		c.JSON(http.StatusOK, gin.H{"code": 0})

	case "search":
		if h.reqClient == nil {
			c.JSON(http.StatusOK, gin.H{"code": 0})
			return
		}
		keyword := strings.TrimSpace(match.Parameters["keyword"])
		h.logger.Info("search requested", zap.String("keyword_hash", shortLogHash(keyword)))
		if keyword == "" {
			card := feishu.NewCardBuilder().
				SetHeader("⚠️ 搜索关键词为空", "orange").
				AddMarkdown("请输入 `/search <关键词>` 搜索需求。").
				Build()
			if err := h.feishuClient.ReplyCard(ctx, messageID, card); err != nil {
				h.logger.Error("send search usage card failed", zap.Error(err))
			}
			c.JSON(http.StatusOK, gin.H{"code": 0})
			return
		}

		resp, err := h.reqClient.SearchRequirements(ctx, keyword, chatID, 1, 5)
		if err != nil {
			h.logger.Error("search requirements failed", zap.Error(err))
			c.JSON(http.StatusOK, gin.H{"code": 0})
			return
		}

		requirements := make([]feishu.Requirement, len(resp.Requirements))
		for i, r := range resp.Requirements {
			requirements[i] = feishu.Requirement{
				ID:          r.Id,
				Title:       r.Title,
				Description: r.Description,
				Status:      r.Status,
				Priority:    r.Priority,
				Category:    r.Category,
			}
		}

		card := feishu.BuildRequirementsSearchCard(keyword, requirements, int(resp.Total))
		if err := h.feishuClient.ReplyCard(ctx, messageID, card); err != nil {
			h.logger.Error("send search card failed", zap.Error(err))
		}

		c.JSON(http.StatusOK, gin.H{"code": 0})

	default:
		h.logger.Debug("skill not implemented", zap.String("skill", match.SkillName))
		c.JSON(http.StatusOK, gin.H{"code": 0})
	}
}

func shortLogHash(value string) string {
	if value == "" {
		return ""
	}
	sum := sha256.Sum256([]byte(value))
	return fmt.Sprintf("%x", sum)[:12]
}

// parseInt converts string to int with error handling.
func parseInt(s string) (int, error) {
	var n int
	_, err := fmt.Sscanf(s, "%d", &n)
	return n, err
}

// respondWithCard returns updated card via v2 callback response format.
func (h *FeishuHandler) respondWithCard(c *gin.Context, card *feishu.Card) {
	c.JSON(http.StatusOK, gin.H{
		"card": gin.H{
			"type": "raw",
			"data": card,
		},
	})
}

// dedupBitableAction checks if a bitable card action is a duplicate (user clicked again).
// Returns true if duplicate. Uses a sha256 hash of action+fields as dedup key with 30s TTL.
func (h *FeishuHandler) dedupBitableAction(c *gin.Context, actionType string, value map[string]interface{}) bool {
	if h.dedup == nil {
		return false
	}
	raw, _ := json.Marshal(value)
	hash := fmt.Sprintf("%x", sha256.Sum256(raw))
	key := fmt.Sprintf("bitable:%s:%s", actionType, hash[:16])
	ctx := c.Request.Context()
	isDup, err := h.dedup.IsDuplicate(ctx, key)
	if err != nil {
		h.logger.Warn("bitable dedup check failed", zap.Error(err))
		return false
	}
	if isDup {
		h.logger.Info("bitable action deduplicated", zap.String("action", actionType))
	}
	return isDup
}

// cardActionContext holds parsed action data common to both v2 and legacy card action handlers.
type cardActionContext struct {
	actionType  string
	reqID       string
	operatorID  string
	actionValue map[string]interface{}
}

// dispatchCardAction contains the shared switch/case logic for card action handling.
// The respond function abstracts how the card is returned (v2 wrapper vs direct JSON).
func (h *FeishuHandler) dispatchCardAction(c *gin.Context, actx *cardActionContext, respond func(*gin.Context, *feishu.Card)) {
	reqCtx := c.Request.Context()

	switch actx.actionType {
	case "confirm":
		if h.reqClient == nil || actx.reqID == "" {
			c.JSON(http.StatusOK, gin.H{"code": 0})
			return
		}
		resp, err := h.reqClient.ConfirmRequirement(reqCtx, actx.reqID, actx.operatorID)
		var card *feishu.Card
		if err != nil {
			h.logger.Error("confirm from card failed", zap.Error(err))
			card = feishu.BuildOperationResultCard("confirm", false, nil, err.Error())
		} else if !resp.Success {
			card = feishu.BuildOperationResultCard("confirm", false, nil, resp.Error)
		} else {
			r := &feishu.Requirement{ID: resp.Requirement.Id, Title: resp.Requirement.Title}
			card = feishu.BuildOperationResultCard("confirm", true, r, "")
		}
		respond(c, card)

	case "reject":
		if h.reqClient == nil || actx.reqID == "" {
			c.JSON(http.StatusOK, gin.H{"code": 0})
			return
		}
		reason, _ := actx.actionValue["reason"].(string)
		resp, err := h.reqClient.RejectRequirement(reqCtx, actx.reqID, reason, actx.operatorID)
		var card *feishu.Card
		if err != nil {
			h.logger.Error("reject from card failed", zap.Error(err))
			card = feishu.BuildOperationResultCard("reject", false, nil, err.Error())
		} else if !resp.Success {
			card = feishu.BuildOperationResultCard("reject", false, nil, resp.Error)
		} else {
			r := &feishu.Requirement{ID: resp.Requirement.Id, Title: resp.Requirement.Title}
			card = feishu.BuildOperationResultCard("reject", true, r, "")
		}
		respond(c, card)

	case "list_page":
		if h.reqClient == nil {
			c.JSON(http.StatusOK, gin.H{"code": 0})
			return
		}
		page := 1
		if p, ok := actx.actionValue["page"].(float64); ok {
			page = int(p)
		}
		resp, err := h.reqClient.ListRequirements(reqCtx, "PENDING", int32(page), 5)
		if err != nil {
			h.logger.Error("list page failed", zap.Error(err))
			c.JSON(http.StatusOK, gin.H{"code": 0})
			return
		}
		requirements := make([]feishu.Requirement, len(resp.Requirements))
		for i, r := range resp.Requirements {
			requirements[i] = feishu.Requirement{
				ID: r.Id, Title: r.Title, Description: r.Description,
				Status: r.Status, Priority: r.Priority, Category: r.Category,
			}
		}
		card := feishu.BuildRequirementsListCard(requirements, page, int(resp.TotalPages), int(resp.Total))
		respond(c, card)

	case "confirm_bitable_update":
		if h.dedupBitableAction(c, "confirm_update", actx.actionValue) {
			card := feishu.NewCardBuilder().SetHeader("✅ 已处理", "green").AddMarkdown("该操作已执行，请勿重复点击").Build()
			respond(c, card)
			return
		}
		recordID, _ := actx.actionValue["record_id"].(string)
		card := h.forwardBitableConfirm(recordID, actx.actionValue, actx.operatorID)
		respond(c, card)

	case "reject_bitable_update":
		card := h.forwardBitableReject(actx.actionValue, actx.operatorID, "update")
		respond(c, card)

	case "confirm_bitable_create":
		if h.dedupBitableAction(c, "confirm_create", actx.actionValue) {
			card := feishu.NewCardBuilder().SetHeader("✅ 已处理", "green").AddMarkdown("该操作已执行，请勿重复点击").Build()
			respond(c, card)
			return
		}
		card := h.forwardBitableCreate(actx.actionValue, actx.operatorID)
		respond(c, card)

	case "reject_bitable_create":
		card := h.forwardBitableReject(actx.actionValue, actx.operatorID, "create")
		respond(c, card)

	case "approve_decomposition":
		wpID, _ := actx.actionValue["wp_id"].(float64)
		if wpID == 0 {
			h.logger.Warn("approve_decomposition missing wp_id")
			c.JSON(http.StatusOK, gin.H{"code": 0})
			return
		}
		card := h.forwardDecompositionAction(int(wpID), "approve", actx.operatorID)
		respond(c, card)

	case "reject_decomposition":
		wpID, _ := actx.actionValue["wp_id"].(float64)
		if wpID == 0 {
			h.logger.Warn("reject_decomposition missing wp_id")
			c.JSON(http.StatusOK, gin.H{"code": 0})
			return
		}
		card := h.forwardDecompositionAction(int(wpID), "reject", actx.operatorID)
		respond(c, card)

	default:
		h.logger.Debug("unhandled card action type", zap.String("action", actx.actionType))
		c.JSON(http.StatusOK, gin.H{"code": 0})
	}
}

// handleCardActionTrigger handles the v2 card.action.trigger event.
// Feishu sends card button clicks as event_callback with event_type=card.action.trigger.
func (h *FeishuHandler) handleCardActionTrigger(c *gin.Context, req *feishu.WebhookRequest) {
	var event feishu.CardActionTriggerEvent
	if err := json.Unmarshal(req.Event, &event); err != nil {
		h.logger.Error("failed to parse card action trigger", zap.Error(err))
		c.JSON(http.StatusOK, gin.H{"code": 0})
		return
	}

	h.logger.Info("card action trigger",
		zap.String("operator", event.Operator.OpenID),
		zap.Any("value", event.Action.Value),
	)

	actx := &cardActionContext{
		actionType:  "",
		reqID:       "",
		operatorID:  event.Operator.OpenID,
		actionValue: event.Action.Value,
	}
	actx.actionType, _ = event.Action.Value["action"].(string)
	actx.reqID, _ = event.Action.Value["requirement_id"].(string)

	h.dispatchCardAction(c, actx, h.respondWithCard)
}

// handleCardAction handles card button click callbacks (legacy format).
func (h *FeishuHandler) handleCardAction(c *gin.Context, req *feishu.WebhookRequest) {
	// Card action callbacks send open_id, token, action etc. at the top level.
	// We must parse from the full raw body, not from req.Action which only
	// contains the inner "action" field.
	rawBody, _ := c.Get("rawBody")
	body, _ := rawBody.([]byte)

	var action feishu.CardAction
	if err := json.Unmarshal(body, &action); err != nil {
		h.logger.Error("failed to parse card action", zap.Error(err))
		c.JSON(http.StatusOK, gin.H{"code": 0})
		return
	}

	h.logger.Info("card action",
		zap.String("user_id", action.UserID),
		zap.Any("value", action.Action.Value),
	)

	actx := &cardActionContext{
		actionType:  "",
		reqID:       "",
		operatorID:  action.OpenID,
		actionValue: action.Action.Value,
	}
	actx.actionType, _ = action.Action.Value["action"].(string)
	actx.reqID, _ = action.Action.Value["requirement_id"].(string)

	h.dispatchCardAction(c, actx, func(c *gin.Context, card *feishu.Card) {
		c.JSON(http.StatusOK, card)
	})
}

// forwardToChatAgent forwards the raw webhook body to chat-agent.
func (h *FeishuHandler) forwardToChatAgent(c *gin.Context) {
	if h.chatAgentAddr == "" {
		h.logger.Debug("chat-agent forwarding skipped, no address configured")
		c.JSON(http.StatusOK, gin.H{"code": 0})
		return
	}

	rawBody, exists := c.Get("rawBody")
	if !exists {
		h.logger.Error("rawBody not found in context")
		c.JSON(http.StatusOK, gin.H{"code": 0})
		return
	}

	body, ok := rawBody.([]byte)
	if !ok {
		h.logger.Error("rawBody has unexpected type", zap.String("type", fmt.Sprintf("%T", rawBody)))
		c.JSON(http.StatusOK, gin.H{"code": 0})
		return
	}
	url := fmt.Sprintf("http://%s/webhook/feishu", h.chatAgentAddr)
	req, err := http.NewRequestWithContext(c.Request.Context(), http.MethodPost, url, bytes.NewReader(body))
	if err != nil {
		h.logger.Error("failed to create forward request", zap.Error(err))
		c.JSON(http.StatusOK, gin.H{"code": 0})
		return
	}
	req.Header.Set("Content-Type", "application/json")
	if h.internalKey != "" {
		req.Header.Set("X-Internal-Key", h.internalKey)
	}
	resp, err := h.httpClient.Do(req)
	if err != nil {
		h.logger.Error("failed to forward to chat-agent", zap.Error(err))
		c.JSON(http.StatusOK, gin.H{"code": 0})
		return
	}
	defer resp.Body.Close()

	h.logger.Info("forwarded to chat-agent", zap.Int("status", resp.StatusCode))
	c.JSON(http.StatusOK, gin.H{"code": 0})
}

// cardActionTimeout is the timeout for card action HTTP requests.
// Feishu enforces a 15s hard deadline on card callbacks; we use 12s
// to leave 3s of margin for network round-trip.
const cardActionTimeout = 12 * time.Second

// forwardBitableConfirm POSTs record_id + fields to chat-agent /api/bitable/confirm
// and returns the response card. On any failure it returns a local error card.
// If the request exceeds the card action timeout, a "processing" card is returned
// so the user sees a graceful message instead of a Feishu timeout error.
func (h *FeishuHandler) forwardBitableConfirm(recordID string, value map[string]interface{}, operatorOpenID string) *feishu.Card {
	if h.chatAgentAddr == "" {
		h.logger.Warn("bitable confirm skipped, no chat-agent address")
		return feishu.NewCardBuilder().
			SetHeader("⚠️ 操作失败", "red").
			AddMarkdown("聊天服务未配置，无法执行更新").
			Build()
	}

	// Extract the fields map from the card action value
	fields, _ := value["fields"].(map[string]interface{})
	if fields == nil {
		fields = map[string]interface{}{}
	}

	payload := map[string]interface{}{
		"record_id": recordID,
		"fields":    fields,
		"user_id":   operatorOpenID,
	}
	if tableID, ok := value["table_id"].(string); ok && tableID != "" {
		payload["table_id"] = tableID
	}
	body, _ := json.Marshal(payload)

	// Use a 12s timeout context to stay within Feishu's 15s card callback limit.
	ctx, cancel := context.WithTimeout(context.Background(), cardActionTimeout)
	defer cancel()

	url := fmt.Sprintf("http://%s/api/bitable/confirm", h.chatAgentAddr)
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, url, bytes.NewReader(body))
	if err != nil {
		h.logger.Error("bitable confirm create request failed", zap.Error(err))
		return feishu.NewCardBuilder().
			SetHeader("⚠️ 操作失败", "red").
			AddMarkdown("创建确认请求失败").
			Build()
	}
	req.Header.Set("Content-Type", "application/json")
	if h.internalKey != "" {
		req.Header.Set("X-Internal-Key", h.internalKey)
	}
	resp, err := h.httpClient.Do(req)
	if err != nil {
		// Graceful degradation: if we timed out, return a "processing" card
		// instead of an error so the user knows the operation is still running.
		if ctx.Err() == context.DeadlineExceeded {
			h.logger.Warn("bitable confirm timed out, returning processing card",
				zap.String("record_id", recordID))
			return buildProcessingCard()
		}
		h.logger.Error("bitable confirm forward failed", zap.Error(err))
		return feishu.NewCardBuilder().
			SetHeader("⚠️ 操作失败", "red").
			AddMarkdown(fmt.Sprintf("转发确认请求失败：%s", err.Error())).
			Build()
	}
	defer resp.Body.Close()

	respBody, err := io.ReadAll(resp.Body)
	if err != nil {
		h.logger.Error("bitable confirm read response failed", zap.Error(err))
		return feishu.NewCardBuilder().
			SetHeader("⚠️ 操作失败", "red").
			AddMarkdown("读取确认响应失败").
			Build()
	}

	// Check HTTP status before parsing — non-200 responses are error JSON, not cards
	if resp.StatusCode != http.StatusOK {
		h.logger.Error("bitable confirm bad status", zap.Int("status", resp.StatusCode), zap.String("body", string(respBody)))
		return feishu.NewCardBuilder().
			SetHeader("⚠️ 操作失败", "red").
			AddMarkdown(fmt.Sprintf("更新服务返回错误 (HTTP %d)", resp.StatusCode)).
			Build()
	}

	var card feishu.Card
	if err := json.Unmarshal(respBody, &card); err != nil {
		h.logger.Error("bitable confirm parse card failed", zap.Error(err))
		return feishu.NewCardBuilder().
			SetHeader("⚠️ 操作失败", "red").
			AddMarkdown("解析确认结果失败").
			Build()
	}

	// Guard against empty card from round-trip (would cause Feishu 200340)
	if card.Header == nil && len(card.Elements) == 0 {
		h.logger.Error("bitable confirm returned empty card", zap.String("body", string(respBody)))
		return feishu.NewCardBuilder().
			SetHeader("⚠️ 操作失败", "red").
			AddMarkdown("更新服务返回了空响应").
			Build()
	}

	h.logger.Info("bitable confirm forwarded", zap.String("record_id", recordID))
	return &card
}

// forwardBitableCreate POSTs fields to chat-agent /api/bitable/create
// and returns the response card. On any failure it returns a local error card.
// Uses cardActionTimeout (12s) to respect Feishu's 15s card callback limit.
func (h *FeishuHandler) forwardBitableCreate(value map[string]interface{}, operatorOpenID string) *feishu.Card {
	if h.chatAgentAddr == "" {
		h.logger.Warn("bitable create skipped, no chat-agent address")
		return feishu.NewCardBuilder().
			SetHeader("⚠️ 操作失败", "red").
			AddMarkdown("聊天服务未配置，无法创建任务").
			Build()
	}

	fields, _ := value["fields"].(map[string]interface{})
	if fields == nil {
		fields = map[string]interface{}{}
	}

	payload := map[string]interface{}{
		"fields":  fields,
		"user_id": operatorOpenID,
	}
	if tableID, ok := value["table_id"].(string); ok && tableID != "" {
		payload["table_id"] = tableID
	}
	body, _ := json.Marshal(payload)

	// Use a 12s timeout context to stay within Feishu's 15s card callback limit.
	ctx, cancel := context.WithTimeout(context.Background(), cardActionTimeout)
	defer cancel()

	url := fmt.Sprintf("http://%s/api/bitable/create", h.chatAgentAddr)
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, url, bytes.NewReader(body))
	if err != nil {
		h.logger.Error("bitable create request failed", zap.Error(err))
		return feishu.NewCardBuilder().
			SetHeader("⚠️ 操作失败", "red").
			AddMarkdown("创建请求构建失败").
			Build()
	}
	req.Header.Set("Content-Type", "application/json")
	if h.internalKey != "" {
		req.Header.Set("X-Internal-Key", h.internalKey)
	}
	resp, err := h.httpClient.Do(req)
	if err != nil {
		if ctx.Err() == context.DeadlineExceeded {
			h.logger.Warn("bitable create timed out, returning processing card")
			return buildProcessingCard()
		}
		h.logger.Error("bitable create forward failed", zap.Error(err))
		return feishu.NewCardBuilder().
			SetHeader("⚠️ 操作失败", "red").
			AddMarkdown(fmt.Sprintf("转发创建请求失败：%s", err.Error())).
			Build()
	}
	defer resp.Body.Close()

	respBody, err := io.ReadAll(resp.Body)
	if err != nil {
		h.logger.Error("bitable create read response failed", zap.Error(err))
		return feishu.NewCardBuilder().
			SetHeader("⚠️ 操作失败", "red").
			AddMarkdown("读取创建响应失败").
			Build()
	}

	if resp.StatusCode != http.StatusOK {
		h.logger.Error("bitable create bad status", zap.Int("status", resp.StatusCode), zap.String("body", string(respBody)))
		return feishu.NewCardBuilder().
			SetHeader("⚠️ 操作失败", "red").
			AddMarkdown(fmt.Sprintf("创建服务返回错误 (HTTP %d)", resp.StatusCode)).
			Build()
	}

	var card feishu.Card
	if err := json.Unmarshal(respBody, &card); err != nil {
		h.logger.Error("bitable create parse card failed", zap.Error(err))
		return feishu.NewCardBuilder().
			SetHeader("⚠️ 操作失败", "red").
			AddMarkdown("解析创建结果失败").
			Build()
	}

	if card.Header == nil && len(card.Elements) == 0 {
		h.logger.Error("bitable create returned empty card", zap.String("body", string(respBody)))
		return feishu.NewCardBuilder().
			SetHeader("⚠️ 操作失败", "red").
			AddMarkdown("创建服务返回了空响应").
			Build()
	}

	h.logger.Info("bitable create forwarded")
	return &card
}

// forwardBitableReject POSTs reject info to chat-agent /api/bitable/reject
// and returns the response card. Falls back to a local card on failure.
func (h *FeishuHandler) forwardBitableReject(value map[string]interface{}, operatorOpenID, actionType string) *feishu.Card {
	if h.chatAgentAddr == "" {
		return feishu.NewCardBuilder().
			SetHeader("🚫 已取消", "grey").
			AddMarkdown("操作已取消").
			Build()
	}

	fields, _ := value["fields"].(map[string]interface{})
	payload := map[string]interface{}{
		"action_type": actionType,
		"user_id":     operatorOpenID,
		"fields":      fields,
	}
	if tableID, ok := value["table_id"].(string); ok && tableID != "" {
		payload["table_id"] = tableID
	}
	if recordID, ok := value["record_id"].(string); ok && recordID != "" {
		payload["record_id"] = recordID
	}
	body, _ := json.Marshal(payload)

	ctx, cancel := context.WithTimeout(context.Background(), cardActionTimeout)
	defer cancel()

	url := fmt.Sprintf("http://%s/api/bitable/reject", h.chatAgentAddr)
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, url, bytes.NewReader(body))
	if err != nil {
		return feishu.NewCardBuilder().
			SetHeader("🚫 已取消", "grey").
			AddMarkdown("操作已取消").
			Build()
	}
	req.Header.Set("Content-Type", "application/json")
	if h.internalKey != "" {
		req.Header.Set("X-Internal-Key", h.internalKey)
	}
	resp, err := h.httpClient.Do(req)
	if err != nil {
		return feishu.NewCardBuilder().
			SetHeader("🚫 已取消", "grey").
			AddMarkdown("操作已取消").
			Build()
	}
	defer resp.Body.Close()

	respBody, err := io.ReadAll(resp.Body)
	if err != nil {
		h.logger.Error("bitable reject read response failed", zap.Error(err))
		return feishu.NewCardBuilder().
			SetHeader("🚫 已取消", "grey").
			AddMarkdown("操作已取消").
			Build()
	}
	var card feishu.Card
	if err := json.Unmarshal(respBody, &card); err != nil {
		return feishu.NewCardBuilder().
			SetHeader("🚫 已取消", "grey").
			AddMarkdown("操作已取消").
			Build()
	}
	return &card
}

// forwardDecompositionAction forwards approve/reject to pjm-agent and returns a result card.
func (h *FeishuHandler) forwardDecompositionAction(wpID int, action string, operator string) *feishu.Card {
	if h.pmAgentAddr == "" {
		h.logger.Warn("pjm-agent forwarding skipped, no address configured")
		return feishu.NewCardBuilder().
			SetHeader("⚠️ 操作失败", "red").
			AddMarkdown("PJM Agent 服务未配置").
			Build()
	}

	payload := map[string]interface{}{
		"operator": operator,
	}
	body, _ := json.Marshal(payload)

	ctx, cancel := context.WithTimeout(context.Background(), cardActionTimeout)
	defer cancel()

	url := fmt.Sprintf("http://%s/api/v1/pm/decompose/%d/%s", h.pmAgentAddr, wpID, action)
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, url, bytes.NewReader(body))
	if err != nil {
		h.logger.Error("decomposition action create request failed", zap.Error(err))
		return feishu.NewCardBuilder().
			SetHeader("⚠️ 操作失败", "red").
			AddMarkdown("创建请求失败").
			Build()
	}
	req.Header.Set("Content-Type", "application/json")
	if h.internalKey != "" {
		req.Header.Set("X-Internal-Key", h.internalKey)
	}
	resp, err := h.httpClient.Do(req)
	if err != nil {
		if ctx.Err() == context.DeadlineExceeded {
			h.logger.Warn("decomposition action timed out, returning processing card",
				zap.Int("wp_id", wpID), zap.String("action", action))
			return buildProcessingCard()
		}
		h.logger.Error("decomposition action forward failed", zap.Error(err), zap.String("action", action))
		return feishu.NewCardBuilder().
			SetHeader("⚠️ 操作失败", "red").
			AddMarkdown(fmt.Sprintf("转发请求失败：%s", err.Error())).
			Build()
	}
	defer resp.Body.Close()

	respBody, err := io.ReadAll(resp.Body)
	if err != nil {
		h.logger.Error("decomposition action read response failed", zap.Error(err))
		return feishu.NewCardBuilder().
			SetHeader("⚠️ 操作失败", "red").
			AddMarkdown("读取响应失败").
			Build()
	}

	if resp.StatusCode != http.StatusOK {
		h.logger.Error("decomposition action bad status",
			zap.Int("status", resp.StatusCode),
			zap.String("body", string(respBody)),
		)
		return feishu.NewCardBuilder().
			SetHeader("⚠️ 操作失败", "red").
			AddMarkdown(fmt.Sprintf("PJM Agent 返回错误 (HTTP %d)", resp.StatusCode)).
			Build()
	}

	// Parse response to get message
	var result struct {
		Success    bool   `json:"success"`
		Action     string `json:"action"`
		Message    string `json:"message"`
		WpID       int    `json:"wp_id"`
		Subject    string `json:"subject"`
		StoryCount int    `json:"story_count"`
		TaskCount  int    `json:"task_count"`
	}
	if err := json.Unmarshal(respBody, &result); err != nil {
		h.logger.Error("decomposition action parse failed", zap.Error(err))
		return feishu.NewCardBuilder().
			SetHeader("⚠️ 操作失败", "red").
			AddMarkdown("解析响应失败").
			Build()
	}

	subtitle := result.Subject
	if subtitle == "" {
		subtitle = fmt.Sprintf("WP #%d", wpID)
	}

	if action == "approve" {
		builder := feishu.NewCardBuilder().
			SetHeaderWithSubtitle("✅ 任务拆解已批准", subtitle, "green").
			AddMarkdown("已写入 OpenProject")
		if result.StoryCount > 0 || result.TaskCount > 0 {
			builder.AddMarkdown(fmt.Sprintf("**%d** 个 User Story，**%d** 个 Task", result.StoryCount, result.TaskCount))
		}
		builder.AddDivider().
			AddNote(fmt.Sprintf("WP #%d · %s", wpID, time.Now().UTC().Format("2006-01-02 15:04 UTC")))
		return builder.Build()
	}

	return feishu.NewCardBuilder().
		SetHeaderWithSubtitle("❌ 任务拆解已拒绝", subtitle, "red").
		AddMarkdown("此拆解方案已被拒绝，可重新触发拆解").
		AddDivider().
		AddNote(fmt.Sprintf("WP #%d · %s", wpID, time.Now().UTC().Format("2006-01-02 15:04 UTC"))).
		Build()
}

// buildProcessingCard returns a temporary card shown when a card action
// request times out. The user sees a friendly "processing" message
// instead of a Feishu timeout error.
func buildProcessingCard() *feishu.Card {
	return feishu.NewCardBuilder().
		SetHeader("⏳ 正在处理中", "blue").
		AddMarkdown("请求正在后台处理，请稍候刷新查看结果...").
		Build()
}
