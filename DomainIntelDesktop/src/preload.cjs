'use strict'

const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('intdogDesktop', {
  credentialStatus: () => ipcRenderer.invoke('intdog:credential-status'),
  saveProvider: value => ipcRenderer.invoke('intdog:save-provider', value),
  clearProvider: () => ipcRenderer.invoke('intdog:clear-provider'),
  relaunch: () => ipcRenderer.invoke('intdog:relaunch'),
})
