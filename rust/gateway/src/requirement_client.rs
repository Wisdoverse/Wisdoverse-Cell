use std::time::Duration;

use tonic::{
    transport::{Channel, Endpoint},
    Request, Status,
};

pub mod proto {
    tonic::include_proto!("requirement");
}

use proto::{
    requirement_service_client::RequirementServiceClient, ConfirmRequest, ExtractRequest,
    ExtractResponse, GetRequest, HealthRequest, HealthResponse, ListRequest, ListResponse,
    OperationResponse, RejectRequest, Requirement, SearchRequest, SearchResponse,
};

#[derive(Clone)]
pub struct RequirementClient {
    inner: RequirementServiceClient<Channel>,
    timeout: Duration,
    extract_timeout: Duration,
}

impl RequirementClient {
    pub fn connect_lazy(addr: &str, timeout: Duration) -> Result<Self, tonic::transport::Error> {
        let endpoint = Endpoint::from_shared(format!("http://{addr}"))?
            .connect_timeout(timeout)
            .timeout(timeout);
        Ok(Self::from_channel(endpoint.connect_lazy(), timeout))
    }

    pub fn from_channel(channel: Channel, timeout: Duration) -> Self {
        Self {
            inner: RequirementServiceClient::new(channel),
            timeout,
            extract_timeout: timeout.saturating_mul(2),
        }
    }

    pub async fn health_check(&self) -> Result<HealthResponse, Status> {
        self.call(self.timeout, |mut client| async move {
            client.health_check(Request::new(HealthRequest {})).await
        })
        .await
    }

    pub async fn list_requirements(
        &self,
        status: impl Into<String>,
        page: i32,
        page_size: i32,
    ) -> Result<ListResponse, Status> {
        let request = ListRequest {
            status: status.into(),
            page,
            page_size,
        };
        self.call(self.timeout, |mut client| async move {
            client.list_requirements(Request::new(request)).await
        })
        .await
    }

    pub async fn get_requirement(&self, id: impl Into<String>) -> Result<Requirement, Status> {
        let request = GetRequest { id: id.into() };
        self.call(self.timeout, |mut client| async move {
            client.get_requirement(Request::new(request)).await
        })
        .await
    }

    pub async fn confirm_requirement(
        &self,
        id: impl Into<String>,
        confirmed_by: impl Into<String>,
    ) -> Result<OperationResponse, Status> {
        let request = ConfirmRequest {
            id: id.into(),
            confirmed_by: confirmed_by.into(),
        };
        self.call(self.timeout, |mut client| async move {
            client.confirm_requirement(Request::new(request)).await
        })
        .await
    }

    pub async fn reject_requirement(
        &self,
        id: impl Into<String>,
        reason: impl Into<String>,
        rejected_by: impl Into<String>,
    ) -> Result<OperationResponse, Status> {
        let request = RejectRequest {
            id: id.into(),
            reason: reason.into(),
            rejected_by: rejected_by.into(),
        };
        self.call(self.timeout, |mut client| async move {
            client.reject_requirement(Request::new(request)).await
        })
        .await
    }

    pub async fn extract_requirements(
        &self,
        content: impl Into<String>,
        source: impl Into<String>,
        context: impl Into<String>,
        participants: Vec<String>,
    ) -> Result<ExtractResponse, Status> {
        let request = ExtractRequest {
            content: content.into(),
            source: source.into(),
            context: context.into(),
            participants,
        };
        self.call(self.extract_timeout, |mut client| async move {
            client.extract_requirements(Request::new(request)).await
        })
        .await
    }

    pub async fn search_requirements(
        &self,
        keyword: impl Into<String>,
        chat_id: impl Into<String>,
        page: i32,
        page_size: i32,
    ) -> Result<SearchResponse, Status> {
        let request = SearchRequest {
            keyword: keyword.into(),
            chat_id: chat_id.into(),
            page,
            page_size,
        };
        self.call(self.timeout, |mut client| async move {
            client.search_requirements(Request::new(request)).await
        })
        .await
    }

    async fn call<T, F, Fut>(&self, timeout: Duration, f: F) -> Result<T, Status>
    where
        F: FnOnce(RequirementServiceClient<Channel>) -> Fut,
        Fut: std::future::Future<Output = Result<tonic::Response<T>, Status>>,
    {
        match tokio::time::timeout(timeout, f(self.inner.clone())).await {
            Ok(Ok(response)) => Ok(response.into_inner()),
            Ok(Err(status)) => Err(status),
            Err(_) => Err(Status::deadline_exceeded("requirement service timeout")),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::{
        proto::{
            requirement_service_server::{RequirementService, RequirementServiceServer},
            ConfirmRequest, ExtractRequest, ExtractResponse, GetRequest, HealthRequest,
            HealthResponse, ListRequest, ListResponse, OperationResponse, RejectRequest,
            Requirement, SearchRequest, SearchResponse,
        },
        RequirementClient,
    };
    use std::{net::SocketAddr, time::Duration};
    use tokio::net::TcpListener;
    use tokio_stream::wrappers::TcpListenerStream;
    use tonic::{Request, Response, Status};

    #[derive(Default)]
    struct MockRequirementService;

    #[tonic::async_trait]
    impl RequirementService for MockRequirementService {
        async fn extract_requirements(
            &self,
            request: Request<ExtractRequest>,
        ) -> Result<Response<ExtractResponse>, Status> {
            let request = request.into_inner();
            Ok(Response::new(ExtractResponse {
                success: true,
                meeting_id: request.source,
                requirements: vec![fixture_requirement(&request.content)],
                questions_count: request.participants.len() as i32,
                error: String::new(),
            }))
        }

        async fn list_requirements(
            &self,
            request: Request<ListRequest>,
        ) -> Result<Response<ListResponse>, Status> {
            let request = request.into_inner();
            Ok(Response::new(ListResponse {
                requirements: vec![fixture_requirement(&request.status)],
                total: request.page_size,
                total_pages: request.page,
            }))
        }

        async fn get_requirement(
            &self,
            request: Request<GetRequest>,
        ) -> Result<Response<Requirement>, Status> {
            Ok(Response::new(fixture_requirement(&request.into_inner().id)))
        }

        async fn confirm_requirement(
            &self,
            request: Request<ConfirmRequest>,
        ) -> Result<Response<OperationResponse>, Status> {
            let request = request.into_inner();
            Ok(Response::new(OperationResponse {
                success: request.confirmed_by == "alice",
                requirement: Some(fixture_requirement(&request.id)),
                error: String::new(),
            }))
        }

        async fn reject_requirement(
            &self,
            request: Request<RejectRequest>,
        ) -> Result<Response<OperationResponse>, Status> {
            let request = request.into_inner();
            Ok(Response::new(OperationResponse {
                success: request.rejected_by == "bob",
                requirement: Some(fixture_requirement(&request.id)),
                error: request.reason,
            }))
        }

        async fn search_requirements(
            &self,
            request: Request<SearchRequest>,
        ) -> Result<Response<SearchResponse>, Status> {
            let request = request.into_inner();
            Ok(Response::new(SearchResponse {
                requirements: vec![fixture_requirement(&request.keyword)],
                total: request.page_size,
            }))
        }

        async fn health_check(
            &self,
            _request: Request<HealthRequest>,
        ) -> Result<Response<HealthResponse>, Status> {
            Ok(Response::new(HealthResponse {
                healthy: true,
                version: "mock".to_string(),
                services: [("db".to_string(), true), ("agent".to_string(), true)]
                    .into_iter()
                    .collect(),
            }))
        }
    }

    #[tokio::test]
    async fn client_matches_requirement_service_contract() {
        let addr = spawn_mock_server().await;
        let client = RequirementClient::connect_lazy(&addr.to_string(), Duration::from_secs(5))
            .expect("build client");

        let health = client.health_check().await.expect("health");
        assert!(health.healthy);
        assert_eq!(health.version, "mock");
        assert_eq!(health.services.get("db"), Some(&true));

        let list = client
            .list_requirements("PENDING", 2, 25)
            .await
            .expect("list");
        assert_eq!(list.total, 25);
        assert_eq!(list.total_pages, 2);
        assert_eq!(list.requirements[0].id, "PENDING");

        let found = client.get_requirement("req-1").await.expect("get");
        assert_eq!(found.id, "req-1");

        let confirmed = client
            .confirm_requirement("req-2", "alice")
            .await
            .expect("confirm");
        assert!(confirmed.success);
        assert_eq!(confirmed.requirement.unwrap().id, "req-2");

        let rejected = client
            .reject_requirement("req-3", "duplicate", "bob")
            .await
            .expect("reject");
        assert!(rejected.success);
        assert_eq!(rejected.error, "duplicate");

        let extracted = client
            .extract_requirements(
                "ship rust gateway",
                "meeting-1",
                "context",
                vec!["alice".to_string(), "bob".to_string()],
            )
            .await
            .expect("extract");
        assert!(extracted.success);
        assert_eq!(extracted.meeting_id, "meeting-1");
        assert_eq!(extracted.questions_count, 2);

        let searched = client
            .search_requirements("gateway", "chat-1", 1, 10)
            .await
            .expect("search");
        assert_eq!(searched.total, 10);
        assert_eq!(searched.requirements[0].id, "gateway");
    }

    async fn spawn_mock_server() -> SocketAddr {
        let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
        let addr = listener.local_addr().unwrap();
        let incoming = TcpListenerStream::new(listener);
        tokio::spawn(async move {
            tonic::transport::Server::builder()
                .add_service(RequirementServiceServer::new(MockRequirementService))
                .serve_with_incoming(incoming)
                .await
                .expect("mock requirement server");
        });
        addr
    }

    fn fixture_requirement(id: &str) -> Requirement {
        Requirement {
            id: id.to_string(),
            title: format!("Requirement {id}"),
            description: "description".to_string(),
            status: "PENDING".to_string(),
            priority: "MEDIUM".to_string(),
            category: "product".to_string(),
            source_quote: "quote".to_string(),
            confirmed_by: String::new(),
            confirmed_at: 0,
            rejection_reason: String::new(),
            created_at: 1,
            updated_at: 2,
        }
    }
}
