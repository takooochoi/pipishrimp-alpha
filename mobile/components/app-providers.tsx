import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { PropsWithChildren } from 'react'
import { MobileWalletProvider } from '@wallet-ui/react-native-kit'

import { AppConfig } from '@/constants/app-config'

const queryClient = new QueryClient()
export function AppProviders({ children }: PropsWithChildren) {
  return (
    <QueryClientProvider client={queryClient}>
      <MobileWalletProvider cluster={AppConfig.cluster} identity={AppConfig.identity}>
        {children}
      </MobileWalletProvider>
    </QueryClientProvider>
  )
}
