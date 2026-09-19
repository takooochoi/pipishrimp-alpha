export type RiskLevel = 'low' | 'medium' | 'high' | 'critical'

export interface ScoreComponents {
  expected_roi: number
  evidence_quality: number
  capital_efficiency: number
  ai_leverage: number
  strategic_value: number
  risk: number
}

export interface Opportunity {
  id: string
  project_id: string | null
  title: string
  category: string
  source_url: string
  source_type: string
  evidence_level: string
  capital_required_usd: number
  estimated_human_minutes: number
  reward_type: string
  reward_certainty: string
  deadline: string | null
  risk_level: RiskLevel
  score_components: ScoreComponents
  bcop_score: number
  recommended_action: string
  fetched_at: string
  is_sample: boolean
  summary: string
}
