import { useMobileWallet } from '@wallet-ui/react-native-kit'
import { useState } from 'react'
import { ActivityIndicator, Pressable, Text, View } from 'react-native'

import { ellipsify } from '@/utils/ellipsify'

import { styles } from './styles'

export function WalletPanel() {
  const { account, connect, disconnect } = useMobileWallet()
  const [isBusy, setIsBusy] = useState(false)
  const [message, setMessage] = useState<string | null>(null)

  async function handleConnect() {
    setIsBusy(true)
    setMessage(null)
    try {
      await connect()
    } catch {
      setMessage('连接已取消或钱包不可用。请确认设备已安装 MWA 钱包。')
    } finally {
      setIsBusy(false)
    }
  }

  async function handleDisconnect() {
    setIsBusy(true)
    setMessage(null)
    try {
      await disconnect()
    } catch {
      setMessage('断开连接失败，请稍后重试。')
    } finally {
      setIsBusy(false)
    }
  }

  return (
    <View style={styles.walletPanel} accessibilityLabel="Wallet connection state">
      <View style={styles.rowBetween}>
        <View style={styles.flexOne}>
          <Text style={styles.sectionEyebrow}>钱包状态</Text>
          {account ? (
            <Text style={styles.walletAddress}>已连接 · {ellipsify(String(account.address), 4, '…')}</Text>
          ) : (
            <Text style={styles.walletMuted}>仅读取 public address，不请求资金操作</Text>
          )}
        </View>
        <Pressable
          accessibilityRole="button"
          disabled={isBusy}
          onPress={account ? handleDisconnect : handleConnect}
          style={({ pressed }) => [
            styles.secondaryButton,
            pressed && styles.buttonPressed,
            isBusy && styles.buttonDisabled,
          ]}
        >
          {isBusy ? (
            <ActivityIndicator color="#0c3b3b" />
          ) : (
            <Text style={styles.secondaryButtonText}>{account ? '断开' : '连接钱包'}</Text>
          )}
        </Pressable>
      </View>
      {message ? <Text style={styles.inlineError}>{message}</Text> : null}
    </View>
  )
}
