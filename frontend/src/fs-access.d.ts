// Minimal ambient types for the File System Access API (Chromium browsers
// only; not yet in TypeScript's default DOM lib). Feature-detected at
// call sites with `"showSaveFilePicker" in window`.
interface SaveFilePickerOptions {
  suggestedName?: string;
}

interface FileSystemWritableFileStream extends WritableStream {
  write(data: Blob | BufferSource | string): Promise<void>;
  close(): Promise<void>;
}

interface FileSystemFileHandle {
  createWritable(): Promise<FileSystemWritableFileStream>;
}

interface Window {
  showSaveFilePicker?(options?: SaveFilePickerOptions): Promise<FileSystemFileHandle>;
}
