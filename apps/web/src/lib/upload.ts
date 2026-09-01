// 文件上传:用 XHR(不用 fetch)是为了拿 upload.onprogress 进度(fetch 原生不报上传进度)。
// 统一通过 BFF /api/upload 透传到知识服务，不向浏览器暴露后端地址。

export interface UploadResult {
  document_id: number;
  filename: string;
  chunk_count: number;
  created_at: string;
}

export const ALLOWED_EXT = [".txt", ".md", ".markdown", ".pdf"];
export const MAX_SIZE = 30 * 1024 * 1024; // 30MB,对齐后端

/** 客户端预校验,给即时反馈(后端也会再校验一次)。返回错误文案或 null。 */
export function validateFile(file: File): string | null {
  const lower = file.name.toLowerCase();
  if (!ALLOWED_EXT.some((ext) => lower.endsWith(ext))) {
    return `只支持 ${ALLOWED_EXT.join(" / ")}`;
  }
  if (file.size > MAX_SIZE) return "文件超过 30MB";
  return null;
}

export function uploadFile(
  file: File,
  onProgress: (pct: number) => void,
): Promise<UploadResult> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/upload");
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) onProgress(Math.round((e.loaded / e.total) * 100));
    };
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          resolve(JSON.parse(xhr.responseText) as UploadResult);
        } catch {
          reject(new Error("返回解析失败"));
        }
      } else {
        reject(new Error(xhr.responseText || `上传失败 HTTP ${xhr.status}`));
      }
    };
    xhr.onerror = () => reject(new Error("网络错误"));
    const fd = new FormData();
    fd.append("file", file);
    xhr.send(fd);
  });
}
