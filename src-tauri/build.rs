fn main() {
    // Ensure the binaries directory exists with placeholder files so Tauri's
    // resource glob doesn't fail during development. In production builds,
    // the real PyInstaller binaries are placed here by scripts/build-sidecar.sh.
    let binaries_dir = std::path::Path::new("binaries");
    if !binaries_dir.exists() {
        std::fs::create_dir_all(binaries_dir).ok();
    }

    // cargo sets TARGET for build scripts. TAURI_ENV_TARGET_TRIPLE is only
    // available to the final compile (via cargo:rustc-env=), not in build.rs,
    // so it would always be empty here.
    let target_triple = std::env::var("TARGET").expect("cargo must set TARGET");

    let ext = if target_triple.contains("windows") {
        ".exe"
    } else {
        ""
    };

    for name in &["legend-lore-sidecar", "legend-lore-mcp"] {
        let path = binaries_dir.join(format!("{}-{}{}", name, target_triple, ext));
        if !path.exists() {
            std::fs::write(&path, "").ok();
        }
    }

    tauri_build::build()
}
