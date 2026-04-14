/**
 * Tauri environment detection and file path utilities.
 *
 * In Tauri context: use the dialog plugin for a real absolute file path.
 * In browser dev context: file paths are not accessible — we fail explicitly.
 */

export function isTauri(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

/**
 * Open a native file dialog and return the absolute path of the selected file.
 * Only works in Tauri context.
 */
export async function openVideoFileDialog(): Promise<string | null> {
  if (!isTauri()) {
    throw new Error(
      "Native file dialog requires the Tauri desktop app. " +
        "Run with: npm run tauri dev"
    );
  }

  // Dynamic import so the module is only loaded in Tauri context
  const { open } = await import("@tauri-apps/plugin-dialog");
  const result = await open({
    multiple: false,
    filters: [
      {
        name: "Video",
        extensions: ["mp4", "mov", "mkv", "avi", "webm"],
      },
    ],
  });

  if (result === null) return null; // user cancelled
  return typeof result === "string" ? result : result[0] ?? null;
}

/**
 * Extract an absolute path from a drag-and-drop File object.
 * In Tauri, File objects expose a non-standard `path` property.
 * In a plain browser, this is unavailable — we return null.
 */
export function getAbsolutePathFromFile(file: File): string | null {
  const maybePath = (file as unknown as { path?: string }).path;
  return typeof maybePath === "string" && maybePath.startsWith("/")
    ? maybePath
    : null;
}
