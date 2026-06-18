const { contextBridge } = require("electron");

contextBridge.exposeInMainWorld("nihaixiaDesktop", {
  platform: process.platform
});
