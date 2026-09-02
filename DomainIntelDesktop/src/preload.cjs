'use strict'

const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('intdogDesktop', {
  credentialStatus: () => ipcRenderer.invoke('intdog:credential-status'),
  saveProvider: value => ipcRenderer.invoke('intdog:save-provider', value),
  clearProvider: () => ipcRenderer.invoke('intdog:clear-provider'),
  selectAgentExecutable: () => ipcRenderer.invoke('intdog:select-agent-executable'),
  backgroundStatus: () => ipcRenderer.invoke('intdog:background-status'),
  requestBackgroundInstall: () => ipcRenderer.invoke('intdog:background-request-install'),
  installBackground: value => ipcRenderer.invoke('intdog:background-install', value),
  removeBackground: () => ipcRenderer.invoke('intdog:background-remove'),
  relaunch: () => ipcRenderer.invoke('intdog:relaunch'),
  close: () => ipcRenderer.invoke('intdog:close'),
})
