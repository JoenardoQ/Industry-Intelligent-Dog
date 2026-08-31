/// <reference types="vite/client" />

interface Window {
  intdogDesktop?: {
    credentialStatus(): Promise<{secureStorage:boolean;configured:boolean;provider:string;model:string;apiBase:string}>
    saveProvider(value:{provider:string;model:string;apiKey:string;apiBase:string}): Promise<unknown>
    clearProvider(): Promise<unknown>
    relaunch(): Promise<boolean>
  }
}
