fn main() -> Result<(), Box<dyn std::error::Error>> {
    tonic_prost_build::compile_protos(
        "../../agents/requirement_manager/grpc/proto/requirement.proto",
    )?;
    Ok(())
}
