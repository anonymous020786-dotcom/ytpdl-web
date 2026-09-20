import { File, Paths } from "expo-file-system";
import * as Sharing from "expo-sharing";

import { api } from "./client";

/** Downloads a finished job's file from the backend into the app's local
 * cache, then opens the native share/save sheet — the mobile equivalent of
 * the web app's browser download or the bot sending the file into chat.
 * There's no universal "Downloads folder" API across iOS/Android for a
 * third-party app, so the share sheet (Save to Files / Save to device /
 * share to another app) is the standard, App-Store-safe way to hand the user
 * a file.
 *
 * Uses expo-file-system's SDK 54+ File/Paths API (File.downloadFileAsync) —
 * the old FileSystem.createDownloadResumable()/downloadAsync() free
 * functions were removed from the default export in this version. */
export async function saveJobFile(
  jobId: string,
  name: string,
  onProgress?: (fraction: number) => void
): Promise<void> {
  const url = await api.fileUrl(jobId, name);
  const destination = new File(Paths.cache, name);

  const file = await File.downloadFileAsync(url, destination, {
    idempotent: true,
    onProgress: (progress) => {
      if (progress.totalBytes > 0) {
        onProgress?.(progress.bytesWritten / progress.totalBytes);
      }
    },
  });

  if (await Sharing.isAvailableAsync()) {
    await Sharing.shareAsync(file.uri);
  }
}
