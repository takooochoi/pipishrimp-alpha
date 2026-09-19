import { Pressable, Text, View } from 'react-native'

import { Opportunity } from '@/types'

import { styles } from './styles'

function riskLabel(risk: Opportunity['risk_level']) {
  return { low: '低', medium: '中', high: '高', critical: '极高' }[risk]
}

export function OpportunityCard({ opportunity, onPress }: { opportunity: Opportunity; onPress: () => void }) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={`查看机会 ${opportunity.title}`}
      onPress={onPress}
      style={({ pressed }) => [styles.opportunityCard, pressed && styles.cardPressed]}
    >
      <View style={styles.rowBetween}>
        <Text style={styles.category}>{opportunity.category}</Text>
        {opportunity.is_sample ? <Text style={styles.sampleBadge}>SAMPLE</Text> : null}
      </View>
      <Text style={styles.cardTitle}>{opportunity.title}</Text>
      <View style={styles.metricGrid}>
        <View style={styles.metric}>
          <Text style={styles.metricLabel}>BCOP Score</Text>
          <Text style={styles.score}>{opportunity.bcop_score.toFixed(0)}</Text>
        </View>
        <View style={styles.metric}>
          <Text style={styles.metricLabel}>风险</Text>
          <Text style={styles.metricValue}>{riskLabel(opportunity.risk_level)}</Text>
        </View>
        <View style={styles.metric}>
          <Text style={styles.metricLabel}>成本</Text>
          <Text style={styles.metricValue}>${opportunity.capital_required_usd.toFixed(0)}</Text>
        </View>
        <View style={styles.metric}>
          <Text style={styles.metricLabel}>人时</Text>
          <Text style={styles.metricValue}>{opportunity.estimated_human_minutes}m</Text>
        </View>
      </View>
      <Text style={styles.rewardText}>{opportunity.reward_type}</Text>
      <Text style={styles.cardLink}>查看证据与详情 →</Text>
    </Pressable>
  )
}
