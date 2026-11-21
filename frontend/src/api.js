export async function api(path, method = "GET", body) {
  const response = await fetch("/api" + path, {
    method,
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body && JSON.stringify(body),
    cache: "no-store",
  })
  if (!response.ok) {
    if (response.status === 401 && !path.startsWith("/auth/")) {
      window.dispatchEvent(new Event("session-ended"))
    }
    const error = await response.json().catch(() => ({}))
    throw Object.assign(new Error(error.detail || "Не удалось выполнить запрос"), {status: response.status})
  }
  return response.status === 204 ? null : response.json()
}

export const money = value => new Intl.NumberFormat("ru-RU", {
  style: "currency", currency: "RUB", minimumFractionDigits: 0, maximumFractionDigits: 2
}).format(value)
export const date = value => new Date(value + "T12:00:00").toLocaleDateString("ru-RU", {
  day: "numeric", month: "long", year: "numeric"
})
