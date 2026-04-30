package handler

import (
	"context"
	"encoding/xml"
	"fmt"
	"net/http"
	"strconv"
	"time"

	pb "github.com/Wisdoverse/project-cell/gateway/api/proto"
	"github.com/Wisdoverse/project-cell/gateway/internal/client"
	"github.com/Wisdoverse/project-cell/gateway/internal/config"
	"github.com/Wisdoverse/project-cell/gateway/internal/service"
	"github.com/Wisdoverse/project-cell/gateway/pkg/wecom"
	"github.com/gin-gonic/gin"
	"go.uber.org/zap"
)

// WecomHandler handles WeChat Work webhook callbacks.
type WecomHandler struct {
	cfg         *config.WecomConfig
	reqClient   *client.RequirementClient
	matcher     *service.Matcher
	sessionMgr  *service.SessionManager
	dedup       *service.Deduplicator
	wecomClient *wecom.Client
	crypto      *wecom.WXBizMsgCrypt
	logger      *zap.Logger
}

// NewWecomHandler creates a new WeChat Work webhook handler.
func NewWecomHandler(
	cfg *config.WecomConfig,
	reqClient *client.RequirementClient,
	matcher *service.Matcher,
	sessionMgr *service.SessionManager,
	dedup *service.Deduplicator,
	logger *zap.Logger,
) (*WecomHandler, error) {
	crypto, err := wecom.NewWXBizMsgCrypt(cfg.Token, cfg.EncodingAESKey, cfg.CorpID)
	if err != nil {
		return nil, fmt.Errorf("init crypto: %w", err)
	}

	return &WecomHandler{
		cfg:         cfg,
		reqClient:   reqClient,
		matcher:     matcher,
		sessionMgr:  sessionMgr,
		dedup:       dedup,
		wecomClient: wecom.NewClient(cfg.CorpID, cfg.AgentID, cfg.Secret),
		crypto:      crypto,
		logger:      logger,
	}, nil
}

// Webhook handles both GET (URL verification) and POST (message callback).
func (h *WecomHandler) Webhook(c *gin.Context) {
	switch c.Request.Method {
	case http.MethodGet:
		h.handleURLVerification(c)
	case http.MethodPost:
		h.handleMessage(c)
	default:
		c.String(http.StatusMethodNotAllowed, "method not allowed")
	}
}

// handleURLVerification handles URL verification from WeChat.
func (h *WecomHandler) handleURLVerification(c *gin.Context) {
	msgSignature := c.Query("msg_signature")
	timestamp := c.Query("timestamp")
	nonce := c.Query("nonce")
	echoStr := c.Query("echostr")

	h.logger.Info("wecom url verification",
		zap.String("timestamp", timestamp),
		zap.String("nonce", nonce),
	)

	plainText, err := h.crypto.VerifyURL(msgSignature, timestamp, nonce, echoStr)
	if err != nil {
		h.logger.Error("url verification failed", zap.Error(err))
		c.String(http.StatusForbidden, "verification failed")
		return
	}

	c.String(http.StatusOK, plainText)
}

// handleMessage handles incoming messages from WeChat.
func (h *WecomHandler) handleMessage(c *gin.Context) {
	msgSignature := c.Query("msg_signature")
	timestamp := c.Query("timestamp")
	nonce := c.Query("nonce")

	// Read body
	body, err := c.GetRawData()
	if err != nil {
		h.logger.Error("failed to read body", zap.Error(err))
		c.String(http.StatusBadRequest, "invalid body")
		return
	}

	// Decrypt message
	plainText, err := h.crypto.DecryptMsg(msgSignature, timestamp, nonce, body)
	if err != nil {
		h.logger.Error("decrypt message failed", zap.Error(err))
		c.String(http.StatusForbidden, "decrypt failed")
		return
	}

	// Parse message
	var msg wecom.ReceivedMessage
	if err := xml.Unmarshal(plainText, &msg); err != nil {
		h.logger.Error("parse message failed", zap.Error(err))
		c.String(http.StatusOK, "success")
		return
	}

	ctx := c.Request.Context()
	msgID := strconv.FormatInt(msg.MsgID, 10)

	// Check for duplicate
	if h.dedup != nil && msg.MsgID > 0 {
		isDup, err := h.dedup.IsDuplicate(ctx, msgID)
		if err != nil {
			h.logger.Warn("dedup check failed", zap.Error(err))
		} else if isDup {
			h.logger.Debug("duplicate message ignored", zap.String("msg_id", msgID))
			c.String(http.StatusOK, "success")
			return
		}
	}

	h.logger.Info("wecom message received",
		zap.String("from", msg.FromUserName),
		zap.String("type", msg.MsgType),
		zap.Int64("msg_id", msg.MsgID),
	)

	// Handle different message types
	switch msg.MsgType {
	case wecom.MsgTypeText, wecom.MsgTypeVoice:
		h.handleTextMessage(c, &msg)
	case wecom.MsgTypeEvent:
		h.handleEvent(c, &msg)
	default:
		h.logger.Debug("unhandled message type", zap.String("type", msg.MsgType))
		c.String(http.StatusOK, "success")
	}
}

// handleTextMessage handles text and voice messages.
func (h *WecomHandler) handleTextMessage(c *gin.Context, msg *wecom.ReceivedMessage) {
	ctx := c.Request.Context()
	content := wecom.ParseMessageContent(msg)
	userID := msg.FromUserName

	// Record message in session
	if h.sessionMgr != nil {
		if err := h.sessionMgr.AddMessage(ctx, "", userID, "user", content); err != nil {
			h.logger.Warn("failed to record message", zap.Error(err))
		}
	}

	// Try to match a skill
	match := h.matcher.Match(content)
	if match != nil {
		h.logger.Info("skill matched",
			zap.String("skill", match.SkillName),
			zap.String("match_type", match.MatchType),
		)

		h.executeSkill(c, match, msg)
		return
	}

	h.logger.Debug("no skill matched", zap.String("content", content))
	c.String(http.StatusOK, "success")
}

// handleEvent handles event messages.
func (h *WecomHandler) handleEvent(c *gin.Context, msg *wecom.ReceivedMessage) {
	h.logger.Info("wecom event",
		zap.String("event", msg.Event),
		zap.String("event_key", msg.EventKey),
	)

	switch msg.Event {
	case wecom.EventTypeClick:
		h.handleClickEvent(c, msg)
	default:
		c.String(http.StatusOK, "success")
	}
}

// handleClickEvent handles menu click events.
func (h *WecomHandler) handleClickEvent(c *gin.Context, msg *wecom.ReceivedMessage) {
	ctx := c.Request.Context()
	userID := msg.FromUserName

	switch msg.EventKey {
	case "list_requirements":
		resp, err := h.reqClient.ListRequirements(ctx, "PENDING", 1, 5)
		if err != nil {
			h.logger.Error("list requirements failed", zap.Error(err))
			c.String(http.StatusOK, "success")
			return
		}

		// Build markdown response
		markdown := h.buildRequirementsMarkdown(resp)
		if err := h.wecomClient.SendMarkdownMessage(ctx, userID, markdown); err != nil {
			h.logger.Error("send markdown failed", zap.Error(err))
		}

	case "help":
		markdown := h.buildHelpMarkdown()
		if err := h.wecomClient.SendMarkdownMessage(ctx, userID, markdown); err != nil {
			h.logger.Error("send help failed", zap.Error(err))
		}
	}

	c.String(http.StatusOK, "success")
}

// executeSkill executes a matched skill.
func (h *WecomHandler) executeSkill(c *gin.Context, match *service.SkillMatch, msg *wecom.ReceivedMessage) {
	ctx := c.Request.Context()
	userID := msg.FromUserName

	switch match.SkillName {
	case "list":
		page := 1
		if p, ok := match.Parameters["page"]; ok {
			if pInt, err := strconv.Atoi(p); err == nil {
				page = pInt
			}
		}

		resp, err := h.reqClient.ListRequirements(ctx, "PENDING", int32(page), 5)
		if err != nil {
			h.logger.Error("list requirements failed", zap.Error(err))
			h.sendErrorMessage(ctx, userID, "获取需求列表失败")
			c.String(http.StatusOK, "success")
			return
		}

		markdown := h.buildRequirementsMarkdown(resp)
		if err := h.wecomClient.SendMarkdownMessage(ctx, userID, markdown); err != nil {
			h.logger.Error("send markdown failed", zap.Error(err))
		}

	case "confirm":
		reqID := match.Parameters["requirement_id"]
		if reqID == "" {
			h.sendErrorMessage(ctx, userID, "请提供需求ID")
			c.String(http.StatusOK, "success")
			return
		}

		resp, err := h.reqClient.ConfirmRequirement(ctx, reqID, userID)
		if err != nil {
			h.logger.Error("confirm failed", zap.Error(err))
			h.sendErrorMessage(ctx, userID, "确认失败: "+err.Error())
		} else if !resp.Success {
			h.sendErrorMessage(ctx, userID, "确认失败: "+resp.Error)
		} else {
			if err := h.wecomClient.SendTextMessage(ctx, userID, fmt.Sprintf("✅ 需求 %s 已确认", reqID)); err != nil {
				h.logger.Error("send confirm message failed", zap.Error(err))
			}
		}

	case "reject":
		reqID := match.Parameters["requirement_id"]
		reason := match.Parameters["reason"]
		if reqID == "" {
			h.sendErrorMessage(ctx, userID, "请提供需求ID")
			c.String(http.StatusOK, "success")
			return
		}

		resp, err := h.reqClient.RejectRequirement(ctx, reqID, reason, userID)
		if err != nil {
			h.logger.Error("reject failed", zap.Error(err))
			h.sendErrorMessage(ctx, userID, "拒绝失败: "+err.Error())
		} else if !resp.Success {
			h.sendErrorMessage(ctx, userID, "拒绝失败: "+resp.Error)
		} else {
			if err := h.wecomClient.SendTextMessage(ctx, userID, fmt.Sprintf("❌ 需求 %s 已拒绝", reqID)); err != nil {
				h.logger.Error("send reject message failed", zap.Error(err))
			}
		}

	case "help":
		markdown := h.buildHelpMarkdown()
		if err := h.wecomClient.SendMarkdownMessage(ctx, userID, markdown); err != nil {
			h.logger.Error("send help markdown failed", zap.Error(err))
		}

	default:
		h.logger.Debug("skill not implemented", zap.String("skill", match.SkillName))
	}

	c.String(http.StatusOK, "success")
}

func (h *WecomHandler) sendErrorMessage(ctx context.Context, userID, msg string) {
	if err := h.wecomClient.SendTextMessage(ctx, userID, "⚠️ "+msg); err != nil {
		h.logger.Error("send error message failed", zap.Error(err))
	}
}

func (h *WecomHandler) buildRequirementsMarkdown(resp *pb.ListResponse) string {
	if len(resp.Requirements) == 0 {
		return "📋 **待确认需求**\n\n暂无待确认的需求 ✨"
	}

	md := fmt.Sprintf("📋 **待确认需求** (%d条)\n\n", resp.Total)
	for i, r := range resp.Requirements {
		priority := h.priorityEmoji(r.Priority)
		md += fmt.Sprintf("%d. **%s** %s\n", i+1, r.Title, priority)
		runes := []rune(r.Description)
		if len(runes) > 50 {
			md += fmt.Sprintf("   %s...\n", string(runes[:50]))
		} else {
			md += fmt.Sprintf("   %s\n", r.Description)
		}
		md += fmt.Sprintf("   ID: `%s`\n\n", r.Id)
	}

	md += fmt.Sprintf("---\n第 1/%d 页 | 回复 `/confirm <ID>` 确认", resp.TotalPages)
	return md
}

func (h *WecomHandler) buildHelpMarkdown() string {
	return `🤖 **Wisdoverse Cell 帮助**

**命令列表：**
- /list - 查看待确认需求
- /confirm <ID> - 确认需求
- /reject <ID> [原因] - 拒绝需求
- /search <关键词> - 搜索需求
- /help - 显示帮助

**快捷触发：**
- 「待确认」「查看需求」→ 显示列表
- 「确认 <ID>」→ 确认需求
- 「拒绝 <ID>」→ 拒绝需求`
}

func (h *WecomHandler) priorityEmoji(p string) string {
	switch p {
	case "P0":
		return "🔴"
	case "P1":
		return "🟠"
	case "P2":
		return "🟡"
	default:
		return "🟢"
	}
}

// ReplyTextMessage creates an XML reply for synchronous response.
func (h *WecomHandler) ReplyTextMessage(c *gin.Context, msg *wecom.ReceivedMessage, content string) {
	timestamp := c.Query("timestamp")
	nonce := c.Query("nonce")

	reply := wecom.NewTextReply(msg.FromUserName, msg.ToUserName, time.Now().Unix(), content)
	replyXML, err := xml.Marshal(reply)
	if err != nil {
		h.logger.Error("marshal reply failed", zap.Error(err))
		c.String(http.StatusOK, "success")
		return
	}

	encrypted, err := h.crypto.EncryptMsg(string(replyXML), timestamp, nonce)
	if err != nil {
		h.logger.Error("encrypt reply failed", zap.Error(err))
		c.String(http.StatusOK, "success")
		return
	}

	c.Data(http.StatusOK, "application/xml", encrypted)
}
