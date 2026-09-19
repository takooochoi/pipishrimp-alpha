import { AppIdentity, createSolanaDevnet, SolanaCluster } from '@wallet-ui/react-native-kit'

export class AppConfig {
  static identity: AppIdentity = { name: 'PipiShrimp Alpha', uri: 'https://pipishrimp.online' }
  static cluster: SolanaCluster = createSolanaDevnet({ url: 'https://api.devnet.solana.com' })
  static apiBaseUrl = process.env.EXPO_PUBLIC_API_BASE_URL ?? 'http://10.0.2.2:8000'
}
