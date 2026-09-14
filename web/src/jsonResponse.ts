/** Thrown when the paper UI received an HTML document instead of a JSON API body. */
export const HTML_AS_JSON_ERROR =
  "API 返回了 HTML 而不是 JSON；请用 `http://127.0.0.1:8000/`（不要只开静态页/错误代理），硬刷新，并重启 `quantit serve`；开发态检查 Vite 是否在代理到仍在听的 8000。";

export function assertJsonResponse(contentType: string | null | undefined, bodyText: string): void {
  const type = (contentType ?? "").toLowerCase();
  const trimmed = (bodyText ?? "").trimStart();
  const looksHtml =
    type.includes("text/html") || trimmed.startsWith("<!") || trimmed.toLowerCase().startsWith("<html");
  if (looksHtml) {
    throw new Error(HTML_AS_JSON_ERROR);
  }
}
