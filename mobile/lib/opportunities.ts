import { AppConfig } from '@/constants/app-config'
import { Opportunity, RiskLevel } from '@/types'

class ApiError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'ApiError'
  }
}

function buildUrl(path: string, params: Record<string, string | undefined> = {}) {
  const url = `${AppConfig.apiBaseUrl}${path}`
  const search = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value) search.set(key, value)
  })
  const query = search.toString()
  return query ? `${url}?${query}` : url
}

async function getJson<T>(url: string): Promise<T> {
  const response = await fetch(url)
  if (!response.ok) throw new ApiError(`API returned ${response.status}`)
  return (await response.json()) as T
}

export function fetchOpportunities(filters: { category?: string; riskLevel?: RiskLevel }) {
  return getJson<Opportunity[]>(
    buildUrl('/v1/opportunities', { category: filters.category, risk_level: filters.riskLevel }),
  )
}

export function fetchOpportunity(id: string) {
  return getJson<Opportunity>(buildUrl(`/v1/opportunities/${encodeURIComponent(id)}`))
}

export { ApiError }
