// Package client provides gRPC clients for communicating with backend services.
package client

import (
	"context"
	"crypto/sha256"
	"fmt"
	"time"

	pb "github.com/Wisdoverse/project-cell/gateway/api/proto"
	"go.uber.org/zap"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
)

// RequirementClient wraps the gRPC client for RequirementService.
type RequirementClient struct {
	conn    *grpc.ClientConn
	client  pb.RequirementServiceClient
	timeout time.Duration
	logger  *zap.Logger
}

// NewRequirementClient creates a new gRPC client for the AI service.
func NewRequirementClient(addr string, timeout time.Duration, logger *zap.Logger) (*RequirementClient, error) {
	conn, err := grpc.NewClient(
		addr,
		grpc.WithTransportCredentials(insecure.NewCredentials()),
	)
	if err != nil {
		return nil, err
	}

	return &RequirementClient{
		conn:    conn,
		client:  pb.NewRequirementServiceClient(conn),
		timeout: timeout,
		logger:  logger,
	}, nil
}

// Close closes the gRPC connection.
func (c *RequirementClient) Close() error {
	return c.conn.Close()
}

// HealthCheck checks if the AI service is healthy.
func (c *RequirementClient) HealthCheck(ctx context.Context) (*pb.HealthResponse, error) {
	ctx, cancel := context.WithTimeout(ctx, c.timeout)
	defer cancel()

	resp, err := c.client.HealthCheck(ctx, &pb.HealthRequest{})
	if err != nil {
		c.logger.Error("health check failed", zap.Error(err))
		return nil, err
	}

	return resp, nil
}

// ListRequirements retrieves requirements with pagination.
func (c *RequirementClient) ListRequirements(ctx context.Context, status string, page, pageSize int32) (*pb.ListResponse, error) {
	ctx, cancel := context.WithTimeout(ctx, c.timeout)
	defer cancel()

	resp, err := c.client.ListRequirements(ctx, &pb.ListRequest{
		Status:   status,
		Page:     page,
		PageSize: pageSize,
	})
	if err != nil {
		c.logger.Error("list requirements failed", zap.Error(err))
		return nil, err
	}

	return resp, nil
}

// GetRequirement retrieves a single requirement by ID.
func (c *RequirementClient) GetRequirement(ctx context.Context, id string) (*pb.Requirement, error) {
	ctx, cancel := context.WithTimeout(ctx, c.timeout)
	defer cancel()

	resp, err := c.client.GetRequirement(ctx, &pb.GetRequest{Id: id})
	if err != nil {
		c.logger.Error("get requirement failed", zap.String("id", id), zap.Error(err))
		return nil, err
	}

	return resp, nil
}

// ConfirmRequirement confirms a requirement.
func (c *RequirementClient) ConfirmRequirement(ctx context.Context, id, confirmedBy string) (*pb.OperationResponse, error) {
	ctx, cancel := context.WithTimeout(ctx, c.timeout)
	defer cancel()

	resp, err := c.client.ConfirmRequirement(ctx, &pb.ConfirmRequest{
		Id:          id,
		ConfirmedBy: confirmedBy,
	})
	if err != nil {
		c.logger.Error("confirm requirement failed", zap.String("id", id), zap.Error(err))
		return nil, err
	}

	return resp, nil
}

// RejectRequirement rejects a requirement with a reason.
func (c *RequirementClient) RejectRequirement(ctx context.Context, id, reason, rejectedBy string) (*pb.OperationResponse, error) {
	ctx, cancel := context.WithTimeout(ctx, c.timeout)
	defer cancel()

	resp, err := c.client.RejectRequirement(ctx, &pb.RejectRequest{
		Id:         id,
		Reason:     reason,
		RejectedBy: rejectedBy,
	})
	if err != nil {
		c.logger.Error("reject requirement failed", zap.String("id", id), zap.Error(err))
		return nil, err
	}

	return resp, nil
}

// ExtractRequirements extracts requirements from content using LLM.
func (c *RequirementClient) ExtractRequirements(ctx context.Context, content, source, ctxInfo string, participants []string) (*pb.ExtractResponse, error) {
	ctx, cancel := context.WithTimeout(ctx, c.timeout*2) // LLM calls need more time
	defer cancel()

	resp, err := c.client.ExtractRequirements(ctx, &pb.ExtractRequest{
		Content:      content,
		Source:       source,
		Context:      ctxInfo,
		Participants: participants,
	})
	if err != nil {
		c.logger.Error("extract requirements failed", zap.Error(err))
		return nil, err
	}

	return resp, nil
}

// SearchRequirements searches requirements by keyword.
func (c *RequirementClient) SearchRequirements(ctx context.Context, keyword, chatID string, page, pageSize int32) (*pb.SearchResponse, error) {
	ctx, cancel := context.WithTimeout(ctx, c.timeout)
	defer cancel()

	resp, err := c.client.SearchRequirements(ctx, &pb.SearchRequest{
		Keyword:  keyword,
		ChatId:   chatID,
		Page:     page,
		PageSize: pageSize,
	})
	if err != nil {
		c.logger.Error("search requirements failed", zap.String("keyword_hash", shortLogHash(keyword)), zap.Error(err))
		return nil, err
	}

	return resp, nil
}

func shortLogHash(value string) string {
	if value == "" {
		return ""
	}
	sum := sha256.Sum256([]byte(value))
	return fmt.Sprintf("%x", sum)[:12]
}
