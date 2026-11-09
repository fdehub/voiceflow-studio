// 封装与 Python pywebview 的原生通信

export function isDesktopApp() {
  return typeof window !== 'undefined' && Boolean(window.pywebview && window.pywebview.api);
}

// 等待 pywebview 就绪
export function waitForApi() {
  if (isDesktopApp()) return Promise.resolve(window.pywebview.api);
  return new Promise((resolve) => {
    const handler = () => {
      window.removeEventListener('pywebviewready', handler);
      resolve(window.pywebview ? window.pywebview.api : null);
    };
    window.addEventListener('pywebviewready', handler);
    // 超时回退（例如在纯浏览器中预览时）
    setTimeout(() => {
      window.removeEventListener('pywebviewready', handler);
      resolve(window.pywebview ? window.pywebview.api : null);
    }, 1500);
  });
}

export const desktopApi = {
  async selectFiles() {
    const api = await waitForApi();
    if (!api) return [];
    return await api.select_files();
  },

  async selectFolder() {
    const api = await waitForApi();
    if (!api) return [];
    return await api.select_folder();
  },

  async resolveDroppedPaths(paths) {
    const api = await waitForApi();
    if (!api) return [];
    return await api.resolve_dropped_paths(paths);
  },

  async resolveDroppedFiles(fileMetas) {
    const api = await waitForApi();
    if (!api) return [];
    if (api.resolve_dropped_files) {
      return await api.resolve_dropped_files(fileMetas);
    }
    const paths = (fileMetas || []).map(f => f.path || f.pywebviewFullPath).filter(Boolean);
    if (paths.length > 0 && api.resolve_dropped_paths) {
      return await api.resolve_dropped_paths(paths);
    }
    return [];
  },

  async startTask(taskId, filePath, engine, exportFormat, keepAudio) {
    const api = await waitForApi();
    if (!api) return { ok: false };
    return await api.start_task(taskId, filePath, engine, exportFormat, keepAudio);
  },

  async cancelTask(taskId) {
    const api = await waitForApi();
    if (!api) return { ok: false };
    return await api.cancel_task(taskId);
  },

  async openInFolder(filePath) {
    const api = await waitForApi();
    if (!api) return false;
    return await api.open_in_folder(filePath);
  },

  async readSubtitleContent(filePath, formatType) {
    const api = await waitForApi();
    if (!api) return { ok: false, error: '桌面桥接未就绪' };
    return await api.read_subtitle_content(filePath, formatType);
  },

  async fastExportTxt(filePath) {
    const api = await waitForApi();
    if (!api) return { ok: false, error: '桌面桥接未就绪' };
    return await api.fast_export_txt(filePath);
  },

  async getConfig() {
    const api = await waitForApi();
    if (!api) return { whisper: {}, bcut_proxies: [], system: {} };
    return await api.get_config();
  },

  async saveConfig(config) {
    const api = await waitForApi();
    if (!api) return { ok: false };
    return await api.save_config(config);
  },

  async testSingleProxy(proxyStr, targetType = 'bcut') {
    const api = await waitForApi();
    if (!api) return { ok: false, message: '桌面桥接未就绪' };
    return await api.test_single_proxy(proxyStr, targetType);
  },

  async checkAppUpdate() {
    const api = await waitForApi();
    if (!api) return { hasUpdate: false, message: '网页预览中' };
    return await api.check_app_update();
  },

  async openExternalUrl(url) {
    const api = await waitForApi();
    if (api && api.open_external_url) {
      return await api.open_external_url(url);
    }
    window.open(url, '_blank');
  },

  async getWorkspaceState() {
    const api = await waitForApi();
    if (!api || !api.get_workspace_state) return {};
    return await api.get_workspace_state();
  },

  async saveWorkspaceState(state) {
    const api = await waitForApi();
    if (!api || !api.save_workspace_state) return { ok: false };
    return await api.save_workspace_state(state);
  }
};

