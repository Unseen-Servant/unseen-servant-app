fn main() {
    // Ensure the binaries directory exists with placeholder files so Tauri's
    // resource glob doesn't fail during development. In production builds,
    // the real PyInstaller binaries are placed here by scripts/build-sidecar.sh.
    let binaries_dir = std::path::Path::new("binaries");
    if !binaries_dir.exists() {
        std::fs::create_dir_all(binaries_dir).ok();
    }

    let target_triple = std::env::var("TAURI_ENV_TARGET_TRIPLE")
        .unwrap_or_else(|_| "aarch64-apple-darwin".to_string());

    for name in &["unseen-sidecar", "unseen-mcp"] {
        let path = binaries_dir.join(format!("{}-{}", name, target_triple));
        if !path.exists() {
            std::fs::write(&path, "").ok();
        }
    }

    tauri_build::build()
}
