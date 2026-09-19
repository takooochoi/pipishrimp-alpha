import { useLocalSearchParams, useRouter } from 'expo-router'
import { useEffect, useState } from 'react'
import { ActivityIndicator, Linking, Pressable, ScrollView, Text, View } from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'

import { colors, styles } from '@/components/styles'
import { fetchOpportunity } from '@/lib/opportunities'
import { Opportunity } from '@/types'

function riskLabel(risk: Opportunity['risk_level']) {
  return { low: '低', medium: '中', high: '高', critical: '极高' }[risk]
}

export default function OpportunityDetailScreen() {
  const router = useRouter()
  const { id } = useLocalSearchParams<{ id: string }>()
  const [opportunity, setOpportunity] = useState<Opportunity | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!id) return
    void fetchOpportunity(id)
      .then(setOpportunity)
      .catch(() => setError('无法加载机会详情，请检查 backend 连接后返回重试。'))
  }, [id])

  if (error)
    return (
      <SafeAreaView style={styles.screen}>
        <View style={[styles.content, styles.stateCard]}>
          <Text style={styles.stateTitle}>详情暂不可用</Text>
          <Text style={styles.stateText}>{error}</Text>
          <Pressable onPress={() => router.back()} style={styles.retryButton}>
            <Text style={styles.retryText}>返回机会列表</Text>
          </Pressable>
        </View>
      </SafeAreaView>
    )
  if (!opportunity)
    return (
      <SafeAreaView style={styles.screen}>
        <View style={[styles.content, styles.stateCard]}>
          <ActivityIndicator color={colors.accent} />
          <Text style={styles.stateTitle}>正在加载详情…</Text>
        </View>
      </SafeAreaView>
    )

  return (
    <SafeAreaView style={styles.screen}>
      <ScrollView contentContainerStyle={styles.content}>
        <Pressable onPress={() => router.back()}>
          <Text style={styles.backLink}>← 返回机会列表</Text>
        </Pressable>
        <View style={styles.detailTop}>
          <View style={styles.rowBetween}>
            <Text style={styles.category}>{opportunity.category}</Text>
            <Text style={styles.sampleBadge}>SAMPLE DATA</Text>
          </View>
          <Text style={styles.detailTitle}>{opportunity.title}</Text>
          <View style={styles.rowBetween}>
            <Text style={styles.subtitle}>证据级别：{opportunity.evidence_level}</Text>
            <View style={styles.detailScore}>
              <Text style={styles.detailScoreLabel}>BCOP SCORE</Text>
              <Text style={styles.detailScoreValue}>{opportunity.bcop_score.toFixed(0)}</Text>
            </View>
          </View>
        </View>
        <View style={styles.detailSection}>
          <Text style={styles.detailSectionTitle}>成本与约束</Text>
          <View style={styles.rowBetween}>
            <Text style={styles.detailLabel}>风险</Text>
            <Text style={styles.detailValue}>{riskLabel(opportunity.risk_level)}</Text>
          </View>
          <View style={styles.rowBetween}>
            <Text style={styles.detailLabel}>资本成本</Text>
            <Text style={styles.detailValue}>${opportunity.capital_required_usd.toFixed(2)} USD</Text>
          </View>
          <View style={styles.rowBetween}>
            <Text style={styles.detailLabel}>预计人工时间</Text>
            <Text style={styles.detailValue}>{opportunity.estimated_human_minutes} 分钟</Text>
          </View>
          <View style={styles.rowBetween}>
            <Text style={styles.detailLabel}>截止时间</Text>
            <Text style={styles.detailValue}>{opportunity.deadline ?? '未设定'}</Text>
          </View>
        </View>
        <View style={styles.detailSection}>
          <Text style={styles.detailSectionTitle}>奖励与证据</Text>
          <Text style={styles.detailBody}>{opportunity.reward_type}</Text>
          <View style={styles.rowBetween}>
            <Text style={styles.detailLabel}>奖励确定性</Text>
            <Text style={styles.detailValue}>{opportunity.reward_certainty}</Text>
          </View>
          <View style={styles.rowBetween}>
            <Text style={styles.detailLabel}>来源类型</Text>
            <Text style={styles.detailValue}>{opportunity.source_type}</Text>
          </View>
          <Text style={styles.detailBody}>{opportunity.summary}</Text>
          <Pressable
            onPress={() =>
              opportunity.source_url.startsWith('https://') && void Linking.openURL(opportunity.source_url)
            }
            style={styles.openSourceButton}
          >
            <Text style={styles.openSourceText}>手动打开来源 →</Text>
          </Pressable>
        </View>
        <View style={styles.detailSection}>
          <Text style={styles.detailSectionTitle}>建议动作</Text>
          <Text style={styles.detailBody}>{opportunity.recommended_action}</Text>
          <Text style={styles.detailBody}>该建议仅用于演示排序与证据查看，不构成个性化投资建议。</Text>
        </View>
      </ScrollView>
    </SafeAreaView>
  )
}
