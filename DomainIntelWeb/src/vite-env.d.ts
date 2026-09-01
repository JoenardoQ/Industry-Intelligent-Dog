/// <reference types="vite/client" />

interface Window {
  intdogDesktop?: {
    credentialStatus(): Promise<{secureStorage:boolean;configured:boolean;provider:string;model:string;apiBase:string;authType:string}>
    saveProvider(value:{provider:string;model:string;apiKey:string;apiBase:string;authType:string}): Promise<unknown>
    clearProvider(): Promise<unknown>
    backgroundStatus(): Promise<{installed:boolean;enabled:boolean;platform:string;errorCategory?:string}>
    requestBackgroundInstall(): Promise<{nonce:string}>
    installBackground(value:{intervalMinutes:number;nonce:string}): Promise<unknown>
    removeBackground(): Promise<unknown>
    relaunch(): Promise<boolean>
    close(): Promise<boolean>
  }
}
