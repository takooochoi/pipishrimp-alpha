import { useRouter } from 'expo-router'
import { useMemo, useState } from 'react'
import { ActivityIndicator, FlatList, Pressable, ScrollView, Text, View } from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'
import { useQuery } from '@tanstack/react-query'

import { OpportunityCard } from '@/components/opportunity-card'
import { colors, styles } from '@/components/styles'
import { WalletPanel } from '@/components/wallet-panel'
import { fetchOpportunities } from '@/lib/opportunities'
import { Opportunity, RiskLevel } from '@/types'

export default function HomeScreen() {
  const router = useRouter()
  const [category, setCategory] = useState<string | undefined>()
  const [riskLevel, setRiskLevel] = useState<RiskLevel | undefined>()
  const {
    data: items = [],
    isLoading,
    error: apiError,
    refetch,
  } = useQuery<Opportunity[]>({
    queryKey: ['opportunities', category, riskLevel],
    queryFn: () => fetchOpportunities({ category, riskLevel }),
  })

  const categories = useMemo(() => ['全部', ...Array.from(new Set(items.map((item) => item.category)))], [items])
  const risks: { label: string; value?: RiskLevel }[] = [
    { label: '全部风险' },
    { label: '低风险', value: 'low' },
    { label: '中风险', value: 'medium' },
    { label: '高风险', value: 'high' },
  ]

  return (
    <SafeAreaView style={styles.screen}>
      <FlatList
        contentContainerStyle={styles.content}
        data={isLoading || apiError ? [] : items}
        keyExtractor={(item) => item.id}
        ListHeaderComponent={
          <View style={styles.header}>
            <Text style={styles.eyebrow}>PIPISHRIMP ALPHA · ANDROID / SEEKER</Text>
            <Text style={styles.title}>现在值得做什么？</Text>
            <Text style={styles.subtitle}>看清成本、证据和风险，再决定是否值得投入时间。</Text>
            <View style={styles.banner}>
              <Text style={styles.bannerTitle}>SAMPLE DATA MODE</Text>
              <Text style={styles.bannerText}>当前机会为演示样例，不代表已验证的活动、奖励或投资建议。</Text>
            </View>
            <WalletPanel />
            <Text style={styles.filterLabel}>按类别筛选</Text>
            <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.filterRow}>
              {categories.map((item) => {
                const value = item === '全部' ? undefined : item
                const active = category === value
                return (
                  <Pressable
                    key={item}
                    onPress={() => setCategory(value)}
                    style={[styles.filterChip, active && styles.filterChipActive]}
                  >
                    <Text style={[styles.filterChipText, active && styles.filterChipTextActive]}>{item}</Text>
                  </Pressable>
                )
              })}
            </ScrollView>
            <Text style={styles.filterLabel}>按风险筛选</Text>
            <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.filterRow}>
              {risks.map((item) => {
                const active = riskLevel === item.value
                return (
                  <Pressable
                    key={item.label}
                    onPress={() => setRiskLevel(item.value)}
                    style={[styles.filterChip, active && styles.filterChipActive]}
                  >
                    <Text style={[styles.filterChipText, active && styles.filterChipTextActive]}>{item.label}</Text>
                  </Pressable>
                )
              })}
            </ScrollView>
          </View>
        }
        ListEmptyComponent={
          <View style={styles.stateCard}>
            {isLoading ? <ActivityIndicator color={colors.accent} /> : null}
            <Text style={styles.stateTitle}>{isLoading ? '正在加载机会…' : '机会数据暂不可用'}</Text>
            <Text style={styles.stateText}>
              {apiError
                ? '暂时无法连接机会 API。请检查 backend 是否运行，或确认手机可以访问配置的 API 地址。'
                : '没有符合当前筛选条件的样例。'}
            </Text>
            {apiError ? (
              <Pressable onPress={() => void refetch()} style={styles.retryButton}>
                <Text style={styles.retryText}>重试</Text>
              </Pressable>
            ) : null}
          </View>
        }
        renderItem={({ item }) => (
          <OpportunityCard opportunity={item} onPress={() => router.push(`/opportunity/${item.id}`)} />
        )}
        ItemSeparatorComponent={() => <View style={{ height: 10 }} />}
        showsVerticalScrollIndicator={false}
      />
    </SafeAreaView>
  )
}
