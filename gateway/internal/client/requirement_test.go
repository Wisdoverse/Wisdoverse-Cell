package client

import (
	"context"
	"net"
	"testing"
	"time"

	pb "github.com/Wisdoverse/project-cell/gateway/api/proto"
	"go.uber.org/zap"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
	"google.golang.org/grpc/test/bufconn"
)

const bufSize = 1024 * 1024

var lis *bufconn.Listener

type mockRequirementServer struct {
	pb.UnimplementedRequirementServiceServer
}

func (s *mockRequirementServer) HealthCheck(ctx context.Context, req *pb.HealthRequest) (*pb.HealthResponse, error) {
	return &pb.HealthResponse{
		Healthy: true,
		Version: "1.0.0",
	}, nil
}

func (s *mockRequirementServer) ListRequirements(ctx context.Context, req *pb.ListRequest) (*pb.ListResponse, error) {
	return &pb.ListResponse{
		Requirements: []*pb.Requirement{
			{
				Id:          "req_001",
				Title:       "Test Requirement",
				Description: "Test Description",
				Status:      req.Status,
				Priority:    "P0",
			},
		},
		Total:      1,
		TotalPages: 1,
	}, nil
}

func (s *mockRequirementServer) GetRequirement(ctx context.Context, req *pb.GetRequest) (*pb.Requirement, error) {
	return &pb.Requirement{
		Id:          req.Id,
		Title:       "Retrieved Requirement",
		Description: "Description",
		Status:      "PENDING",
		Priority:    "P1",
	}, nil
}

func (s *mockRequirementServer) ConfirmRequirement(ctx context.Context, req *pb.ConfirmRequest) (*pb.OperationResponse, error) {
	return &pb.OperationResponse{
		Success: true,
		Requirement: &pb.Requirement{
			Id:     req.Id,
			Title:  "Confirmed",
			Status: "CONFIRMED",
		},
	}, nil
}

func (s *mockRequirementServer) RejectRequirement(ctx context.Context, req *pb.RejectRequest) (*pb.OperationResponse, error) {
	return &pb.OperationResponse{
		Success: true,
		Requirement: &pb.Requirement{
			Id:     req.Id,
			Title:  "Rejected",
			Status: "REJECTED",
		},
	}, nil
}

func (s *mockRequirementServer) ExtractRequirements(ctx context.Context, req *pb.ExtractRequest) (*pb.ExtractResponse, error) {
	return &pb.ExtractResponse{
		Success: true,
		Requirements: []*pb.Requirement{
			{
				Id:          "req_extracted",
				Title:       "Extracted Requirement",
				Description: "From content",
				Priority:    "P2",
				Category:    "feature",
			},
		},
	}, nil
}

func (s *mockRequirementServer) SearchRequirements(ctx context.Context, req *pb.SearchRequest) (*pb.SearchResponse, error) {
	return &pb.SearchResponse{
		Requirements: []*pb.Requirement{
			{
				Id:          "req_search_001",
				Title:       "Search Result",
				Description: "Matches: " + req.Keyword,
				Status:      "PENDING",
			},
		},
		Total: 1,
	}, nil
}

func init() {
	lis = bufconn.Listen(bufSize)
	s := grpc.NewServer()
	pb.RegisterRequirementServiceServer(s, &mockRequirementServer{})
	go func() {
		if err := s.Serve(lis); err != nil {
			panic(err)
		}
	}()
}

func bufDialer(context.Context, string) (net.Conn, error) {
	return lis.Dial()
}

func setupTestClient(t *testing.T) *RequirementClient {
	//nolint:staticcheck // grpc.Dial is deprecated but required for bufconn testing
	conn, err := grpc.Dial(
		"bufnet",
		grpc.WithContextDialer(bufDialer),
		grpc.WithTransportCredentials(insecure.NewCredentials()),
	)
	if err != nil {
		t.Fatalf("failed to dial: %v", err)
	}

	return &RequirementClient{
		conn:    conn,
		client:  pb.NewRequirementServiceClient(conn),
		timeout: 5 * time.Second,
		logger:  zap.NewNop(),
	}
}

func TestRequirementClient_HealthCheck(t *testing.T) {
	client := setupTestClient(t)
	defer client.Close()

	ctx := context.Background()
	resp, err := client.HealthCheck(ctx)
	if err != nil {
		t.Fatalf("HealthCheck failed: %v", err)
	}

	if !resp.Healthy {
		t.Error("expected healthy = true")
	}

	if resp.Version != "1.0.0" {
		t.Errorf("version = %q, want 1.0.0", resp.Version)
	}
}

func TestRequirementClient_ListRequirements(t *testing.T) {
	client := setupTestClient(t)
	defer client.Close()

	ctx := context.Background()
	resp, err := client.ListRequirements(ctx, "PENDING", 1, 10)
	if err != nil {
		t.Fatalf("ListRequirements failed: %v", err)
	}

	if len(resp.Requirements) != 1 {
		t.Errorf("requirements count = %d, want 1", len(resp.Requirements))
	}

	if resp.Requirements[0].Id != "req_001" {
		t.Errorf("id = %q, want req_001", resp.Requirements[0].Id)
	}

	if resp.Requirements[0].Status != "PENDING" {
		t.Errorf("status = %q, want PENDING", resp.Requirements[0].Status)
	}
}

func TestRequirementClient_GetRequirement(t *testing.T) {
	client := setupTestClient(t)
	defer client.Close()

	ctx := context.Background()
	resp, err := client.GetRequirement(ctx, "req_123")
	if err != nil {
		t.Fatalf("GetRequirement failed: %v", err)
	}

	if resp.Id != "req_123" {
		t.Errorf("id = %q, want req_123", resp.Id)
	}
}

func TestRequirementClient_ConfirmRequirement(t *testing.T) {
	client := setupTestClient(t)
	defer client.Close()

	ctx := context.Background()
	resp, err := client.ConfirmRequirement(ctx, "req_456", "user123")
	if err != nil {
		t.Fatalf("ConfirmRequirement failed: %v", err)
	}

	if !resp.Success {
		t.Error("expected success = true")
	}

	if resp.Requirement.Status != "CONFIRMED" {
		t.Errorf("status = %q, want CONFIRMED", resp.Requirement.Status)
	}
}

func TestRequirementClient_RejectRequirement(t *testing.T) {
	client := setupTestClient(t)
	defer client.Close()

	ctx := context.Background()
	resp, err := client.RejectRequirement(ctx, "req_789", "Not in scope", "user456")
	if err != nil {
		t.Fatalf("RejectRequirement failed: %v", err)
	}

	if !resp.Success {
		t.Error("expected success = true")
	}

	if resp.Requirement.Status != "REJECTED" {
		t.Errorf("status = %q, want REJECTED", resp.Requirement.Status)
	}
}

func TestRequirementClient_ExtractRequirements(t *testing.T) {
	client := setupTestClient(t)
	defer client.Close()

	ctx := context.Background()
	resp, err := client.ExtractRequirements(ctx, "We need to add a new feature for offline mode", "chat", "", []string{"user1"})
	if err != nil {
		t.Fatalf("ExtractRequirements failed: %v", err)
	}

	if !resp.Success {
		t.Error("expected success = true")
	}

	if len(resp.Requirements) != 1 {
		t.Errorf("requirements count = %d, want 1", len(resp.Requirements))
	}
}

func TestRequirementClient_SearchRequirements(t *testing.T) {
	client := setupTestClient(t)
	defer client.Close()

	ctx := context.Background()
	resp, err := client.SearchRequirements(ctx, "offline", "chat123", 1, 10)
	if err != nil {
		t.Fatalf("SearchRequirements failed: %v", err)
	}

	if len(resp.Requirements) != 1 {
		t.Errorf("requirements count = %d, want 1", len(resp.Requirements))
	}

	if resp.Requirements[0].Id != "req_search_001" {
		t.Errorf("id = %q, want req_search_001", resp.Requirements[0].Id)
	}
}

func TestRequirementClient_Close(t *testing.T) {
	client := setupTestClient(t)

	err := client.Close()
	if err != nil {
		t.Errorf("Close failed: %v", err)
	}
}
