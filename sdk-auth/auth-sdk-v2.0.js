/**
 * AuthSDK - 登录授权 SDK
 *
 * 提供给其他系统接入调用，功能：
 * 1. 仅当 URL 路径含有 "data-ai" 时启用登录校验；不含该路径时 SDK 直接放行（不弹窗、不校验）
 * 2. 页面加载时检查用户是否已通过「邮箱 + 验证码」登录（凭据存于 localStorage）
 * 3. 未登录时强制弹出登录弹窗（可切换到「申请体验」表单）
 * 4. 未登录时阻塞业务代码执行（AuthSDK.ready() Promise 挂起，业务 JS 不加载）
 * 5. financeToken 具有 30 分钟有效期：恢复凭据时校验是否过期，页面停留期间到点自动登出弹窗重新登录
 * 6. 弹窗不可被用户通过常规手段（ESC、点击遮罩、DevTools 删除 DOM）关闭
 *
 * 接入方式（零配置，直接引入即可运行）：
 *   <script src="auth-sdk.js"></script>
 *   <!-- 接口地址已内置为默认配置（DEFAULT_CONFIG），无需调用 init -->
 *
 * 如需覆盖默认配置（可选）：
 *   <script src="auth-sdk.js"></script>
 *   <script>
 *     AuthSDK.init({ loginApi: 'https://your-api/login', useMock: true });
 *   </script>
 *
 * 业务 JS 建议通过 ready() 动态加载，实现「未登录不加载业务」：
 *   AuthSDK.ready().then(user => loadScript('business.js'));
 */
(function (global) {
  'use strict';

  var STORAGE_KEY = 'auth_sdk_credentials';

  /**
   * 内置默认接口配置：接入方直接引入 SDK 即可运行，无需调用 init 配置。
   * 如需覆盖某项，调用 AuthSDK.init({ loginApi: '...' }) 即可（未传项仍用默认值）。
   */
  var DEFAULT_CONFIG = {
    // 申请体验码（申请Tab，表单编码）：POST { email, username, phone, reason }
    applyApi: '/authApi/register',
    // 获取动态验证码（登录面板按钮，表单编码）：POST { email }
    codeApi: '/authApi/login/send_code',
    // 体验码登录（表单编码）：POST { email, code }
    // 成功返回：{ message, financeToken, username, email, expires_in }
    loginApi: '/authApi/login',
    // 登录态校验：GET /authApi/check_login?token=xxx -> { valid, email, username, expires_at }
    checkLoginApi: '/authApi/check_login'
  };

  /* ---------------- 工具函数 ---------------- */

  function el(tag, attrs, children) {
    var node = document.createElement(tag);
    if (attrs) {
      Object.keys(attrs).forEach(function (k) {
        if (k === 'style') node.setAttribute('style', attrs[k]);
        else if (k === 'text') node.textContent = attrs[k];
        else node.setAttribute(k, attrs[k]);
      });
    }
    (children || []).forEach(function (c) { if (c) node.appendChild(c); });
    return node;
  }

  function isValidEmail(email) {
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
  }

  function isValidPhone(phone) {
    // 中国大陆手机号：1 开头 11 位数字
    return /^1[3-9]\d{9}$/.test(phone);
  }

  function randomCode() {
    // 生成 6 位数字验证码（mock 使用）
    return String(Math.floor(100000 + Math.random() * 900000));
  }

  /* ---------------- Mock 实现（演示环境，无需后端） ---------------- */

  var mockDB = {}; // { email: { code, username } }

  var mockApi = {
    applyCode: function (body) {
      return new Promise(function (resolve) {
        setTimeout(function () {
          var code = randomCode();
          mockDB[body.email] = { code: code, username: body.username };
          // 真实场景验证码会发送到邮箱，mock 直接返回便于演示
          resolve({ code: 0, message: 'ok', data: { code: code } });
        }, 400);
      });
    },
    sendCode: function (body) {
      return new Promise(function (resolve) {
        setTimeout(function () {
          var code = randomCode();
          mockDB[body.email] = mockDB[body.email] || {};
          mockDB[body.email].code = code;
          // 真实场景验证码会发送到邮箱，mock 直接返回便于演示
          resolve({ code: 0, message: '验证码已发送至您的邮箱', data: { code: code } });
        }, 400);
      });
    },
    checkLogin: function (financeToken) {
      return new Promise(function (resolve) {
        setTimeout(function () {
          if (financeToken && financeToken.indexOf('mock-finance-token-') === 0) {
            resolve({
              valid: true,
              email: 'demo@example.com',
              username: '演示用户',
              expires_at: new Date(Date.now() + 30 * 60 * 1000).toISOString()
            });
          } else {
            resolve({ valid: false });
          }
        }, 300);
      });
    },
    login: function (body) {
      return new Promise(function (resolve, reject) {
        setTimeout(function () {
          var email = body.email;
          if (mockDB[email] && mockDB[email].code === body.code) {
            resolve({
              code: 0,
              message: '登录成功',
              financeToken: 'mock-finance-token-' + Date.now(),
              username: mockDB[email].username || '',
              email: email,
              expires_in: 1800
            });
          } else {
            reject({ code: 40001, message: '验证码无效或已过期，请重新获取' });
          }
        }, 400);
      });
    }
  };

  /* ---------------- SDK 主体 ---------------- */

  function AuthSDK() {
    this._config = {};
    this._inited = false; // 是否已初始化（显式 init 或自动初始化）
    this._readyPromise = null;
    this._readyResolve = null;
    this._overlay = null;
    this._observer = null;
    this._modalVisible = false;
    this._user = null;
    this._sessionTimer = null; // 会话过期定时器（页面停留期间到点自动登出）
    this._pendingMsg = '';     // 重新弹窗时展示的提示（如“登录已过期”）
  }

  /**
   * 初始化 SDK
   * @param {Object} [config] 可选配置，未传项使用内置默认值（DEFAULT_CONFIG）：
   *   { applyApi, codeApi, loginApi, checkLoginApi, useMock }
   *   直接调用 AuthSDK.init() 或依赖自动初始化均可，零配置运行
   */
  AuthSDK.prototype.init = function (config) {
    // 默认配置 + 用户配置浅合并（用户传入项覆盖默认值）
    var cfg = {};
    Object.keys(DEFAULT_CONFIG).forEach(function (k) { cfg[k] = DEFAULT_CONFIG[k]; });
    if (config) {
      Object.keys(config).forEach(function (k) { cfg[k] = config[k]; });
    }
    this._config = cfg;
    this._inited = true;
    // 页面加载时立即建立 ready Promise，业务方挂起等待
    this._bootReadyPromise();
    return this;
  };

  AuthSDK.prototype._bootReadyPromise = function () {
    var self = this;
    this._readyPromise = new Promise(function (resolve) {
      self._readyResolve = resolve;
    });

    // URL 路径不含 "data-ai"：不做登录校验，直接放行（SDK 视同未启用）
    if (!this._hasDataAiPath()) {
      this._user = { skipped: true };
      this._readyResolve(this._user);
      return;
    }

    // 等待 DOM 就绪后再渲染弹窗
    var showModal = function () {
      if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function () { self._showModal(); });
      } else {
        self._showModal();
      }
    };

    // 检查登录态：已登录 -> 放行业务；未登录 -> 弹窗拦截
    var urlFinanceToken = this._getFinanceTokenFromUrl();
    if (urlFinanceToken) {
      // URL 携带 financeToken：调用 check_login 接口校验登录态
      this._checkLogin(urlFinanceToken)
        .then(function (json) {
          if (json && json.valid) {
            // 校验通过：保存 financeToken（localStorage key = "financeToken"）并放行页面访问
            self._onLoginSuccess({
              email: json.email || '',
              financeToken: urlFinanceToken,
              username: json.username || '',
              expires_at: json.expires_at || ''
            });
          } else {
            showModal();
          }
        })
        .catch(function () { showModal(); });
      return;
    }

    if (this.isLoggedIn()) {
      var localFinanceToken = this._user.financeToken;
      if (localFinanceToken && (this._config.checkLoginApi || this._config.useMock)) {
        // 本地存在 financeToken：进入页面时仍需调用 check_login 实时校验（服务端鉴权）
        this._checkLogin(localFinanceToken)
          .then(function (json) {
            if (json && json.valid) {
              // 校验通过：保留原登录时间，用服务端返回刷新用户信息与凭据
              self._user.email = json.email || self._user.email;
              self._user.username = json.username || self._user.username;
              if (json.expires_at) self._user.expires_at = json.expires_at;
              global.localStorage.setItem('financeToken', self._user.financeToken);
              global.localStorage.setItem(STORAGE_KEY, JSON.stringify(self._user));
              self._startSessionTimer();
              self._readyResolve(self._user);
            } else {
              // 服务端判定已失效：清除本地凭据并弹窗重新登录
              self._clearCredentials();
              self._pendingMsg = '登录已失效，请重新登录';
              showModal();
            }
          })
          .catch(function () {
            // 校验接口异常：按未登录处理，弹窗拦截（保留凭据以便刷新后重试）
            showModal();
          });
      } else {
        // 未配置 checkLoginApi：退化为仅本地校验
        this._readyResolve(this._user);
      }
    } else {
      showModal();
    }
  };

  /** 判断 URL 路径中是否含有 "data-ai" 路径段 */
  AuthSDK.prototype._hasDataAiPath = function () {
    try {
      return global.location.pathname.indexOf('data-ai') !== -1;
    } catch (e) { return false; }
  };

  /** 从浏览器 URL 中提取 financeToken 参数（?financeToken=xxx） */
  AuthSDK.prototype._getFinanceTokenFromUrl = function () {
    try {
      var m = global.location.search.match(/[?&]financeToken=([^&]+)/);
      return m ? decodeURIComponent(m[1]) : '';
    } catch (e) { return ''; }
  };

  /** 调用 check_login 接口校验 financeToken 登录态（GET checkLoginApi?token=xxx） */
  AuthSDK.prototype._checkLogin = function (financeToken) {
    var cfg = this._config;
    if (cfg.useMock) return mockApi.checkLogin(financeToken);
    if (!cfg.checkLoginApi) return Promise.reject({ message: '未配置 checkLoginApi' });
    return fetch(cfg.checkLoginApi + '?token=' + encodeURIComponent(financeToken), {
      method: 'GET'
    })
      .then(function (res) {
        return res.text().then(function (text) {
          var json;
          try { json = JSON.parse(text); }
          catch (e) { throw { message: 'check_login 接口响应格式错误' }; }
          if (!res.ok) throw { message: ('请求失败(' + res.status + ')') };
          return json; // 由调用方根据 valid 字段判断
        });
      });
  };

  /** 读取本地凭据判断是否已登录（含 30 分钟有效期校验，过期视为未登录） */
  AuthSDK.prototype.isLoggedIn = function () {
    try {
      var raw = global.localStorage.getItem(STORAGE_KEY);
      if (!raw) return false;
      var cred = JSON.parse(raw);
      if (cred && cred.email) {
        this._user = {
          email: cred.email,
          financeToken: cred.financeToken || global.localStorage.getItem('financeToken') || '',
          username: cred.username,
          expires_in: cred.expires_in || 0,
          expires_at: cred.expires_at || '',
          login_at: cred.login_at || 0
        };
        if (this._isExpired()) {
          // 凭据已过期：清除并要求重新登录
          this._clearCredentials();
          this._pendingMsg = '登录已过期，请重新登录';
          return false;
        }
        return true;
      }
    } catch (e) { /* 凭据损坏视为未登录 */ }
    return false;
  };

  /**
   * 判断当前登录态是否已过期
   * 优先使用 expires_at（check_login 返回的绝对时间），
   * 其次使用 login_at + expires_in 计算，expires_in 缺省按 1800 秒（30 分钟）计
   */
  AuthSDK.prototype._isExpired = function () {
    var u = this._user;
    if (!u) return true;
    if (u.expires_at) {
      var t = Date.parse(u.expires_at);
      if (!isNaN(t)) return Date.now() >= t;
    }
    if (!u.login_at) return false;
    var life = (u.expires_in || 1800) * 1000;
    return Date.now() >= u.login_at + life;
  };

  /** 计算剩余有效时长（毫秒），用于会话过期定时器 */
  AuthSDK.prototype._sessionRemainMs = function () {
    var u = this._user;
    if (!u) return 0;
    if (u.expires_at) {
      var t = Date.parse(u.expires_at);
      if (!isNaN(t)) return t - Date.now();
    }
    if (!u.login_at) return 0;
    return u.login_at + (u.expires_in || 1800) * 1000 - Date.now();
  };

  /** 清除本地凭据（含独立存储的 financeToken） */
  AuthSDK.prototype._clearCredentials = function () {
    global.localStorage.removeItem(STORAGE_KEY);
    global.localStorage.removeItem('financeToken');
    this._user = null;
  };

  /** 启动会话过期定时器：页面停留期间到点自动登出并弹窗重新登录 */
  AuthSDK.prototype._startSessionTimer = function () {
    this._stopSessionTimer();
    var remain = this._sessionRemainMs();
    if (remain <= 0) return;
    var self = this;
    this._sessionTimer = setTimeout(function () {
      self._stopSessionTimer();
      self._clearCredentials();
      self._pendingMsg = '登录已过期，请重新登录';
      self._bootReadyPromise();
    }, remain);
  };

  /** 停止会话过期定时器 */
  AuthSDK.prototype._stopSessionTimer = function () {
    if (this._sessionTimer) {
      clearTimeout(this._sessionTimer);
      this._sessionTimer = null;
    }
  };

  /**
   * 业务方入口：返回 Promise，登录成功后 resolve(user)
   * 业务 JS 必须写在该 Promise 的 then 中（或由其触发动态加载），从而实现"未登录不加载业务"
   */
  AuthSDK.prototype.ready = function () {
    return this._readyPromise;
  };

  /** 获取当前登录用户信息 */
  AuthSDK.prototype.getUser = function () {
    return this._user;
  };

  /** 登出：清除凭据（含 financeToken）、停止会话定时器并重新拉起登录弹窗 */
  AuthSDK.prototype.logout = function () {
    this._stopSessionTimer();
    this._clearCredentials();
    this._bootReadyPromise();
  };

  /** 统一的 POST 请求封装，兼容自定义接口与 mock（真实接口为表单编码格式） */
  AuthSDK.prototype._post = function (url, body) {
    if (this._config.useMock) {
      if (url === '__apply__') return mockApi.applyCode(body);
      if (url === '__sendcode__') return mockApi.sendCode(body);
      return mockApi.login(body);
    }
    // 后端接口要求 application/x-www-form-urlencoded 格式
    var form = [];
    Object.keys(body).forEach(function (k) {
      if (body[k] !== undefined && body[k] !== null) {
        form.push(encodeURIComponent(k) + '=' + encodeURIComponent(body[k]));
      }
    });
    return fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: form.join('&')
    }).then(function (res) {
      return res.text().then(function (text) {
        var json;
        try { json = JSON.parse(text); }
        catch (e) { throw { message: '接口响应格式错误' }; }
        // 后端失败时返回 { error: "..." }
        if (!res.ok || json.error) {
          throw { message: json.error || ('请求失败(' + res.status + ')') };
        }
        return json;
      });
    });
  };

  /** 申请体验（申请Tab 使用：email + username + phone + reason） */
  AuthSDK.prototype.applyCode = function (email, username, phone, reason) {
    var cfg = this._config;
    var body = { email: email, username: username, phone: phone || '', reason: reason || '' };
    if (cfg.useMock) return this._post('__apply__', body);
    if (!cfg.applyApi) return Promise.reject({ message: '未配置 applyApi' });
    return this._post(cfg.applyApi, body);
  };

  /** 获取动态验证码（登录面板「获取验证码」按钮使用：email） */
  AuthSDK.prototype.sendCode = function (email) {
    var cfg = this._config;
    var body = { email: email };
    if (cfg.useMock) return this._post('__sendcode__', body);
    if (!cfg.codeApi) return Promise.reject({ message: '未配置 codeApi' });
    return this._post(cfg.codeApi, body);
  };

  /** 登录成功后调用：落盘凭据（financeToken 单独存 localStorage key = "financeToken"）、放行业务、销毁弹窗 */
  AuthSDK.prototype._onLoginSuccess = function (data) {
    this._user = {
      email: data.email,
      financeToken: data.financeToken || '',
      username: data.username || '',
      expires_in: data.expires_in || 0,
      expires_at: data.expires_at || '',
      login_at: Date.now()
    };
    // financeToken 独立存储，供业务系统直接读取 localStorage.getItem('financeToken')
    global.localStorage.setItem('financeToken', this._user.financeToken);
    global.localStorage.setItem(STORAGE_KEY, JSON.stringify(this._user));
    // 启动会话过期定时器（30 分钟到点自动登出并弹窗重新登录）
    this._startSessionTimer();
    this._destroyModal();
    this._readyResolve(this._user);
  };

  /* ================= 弹窗 UI ================= */

  AuthSDK.prototype._showModal = function () {
    if (this._modalVisible) return;
    this._modalVisible = true;

    var overlay = this._overlay = this._buildModal();
    document.body.appendChild(overlay);
    this._lockPage();
    this._startProtect();
  };

  AuthSDK.prototype._buildModal = function () {
    var self = this;

    /* --- 样式 --- */
    var css = [
      '.asdk-overlay{position:fixed;inset:0;background:rgba(15,23,42,.72);backdrop-filter:blur(3px);',
      'z-index:2147483647;display:flex;align-items:center;justify-content:center;',
      'font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;}',
      '.asdk-card{width:360px;max-width:calc(100vw - 32px);background:#fff;border-radius:16px;',
      'padding:32px 28px;box-shadow:0 24px 64px rgba(0,0,0,.28);box-sizing:border-box;}',
      '.asdk-logo{width:44px;height:44px;border-radius:12px;background:#4f46e5;',
      'display:flex;align-items:center;justify-content:center;margin:0 auto 12px;line-height:1;}',
      '.asdk-title{text-align:center;font-size:18px;font-weight:600;color:#0f172a;margin:0 0 4px;}',
      '.asdk-sub{text-align:center;font-size:13px;color:#64748b;margin:0 0 20px;}',
      '.asdk-tabs{display:flex;background:#f1f5f9;border-radius:10px;padding:4px;margin-bottom:20px;}',
      '.asdk-tab{flex:1;border:0;background:transparent;padding:8px 0;font-size:13px;color:#64748b;',
      'border-radius:8px;cursor:pointer;transition:all .2s;}',
      '.asdk-tab.active{background:#fff;color:#4f46e5;font-weight:600;box-shadow:0 1px 4px rgba(0,0,0,.08);}',
      '.asdk-field{margin-bottom:14px;text-align:left;}',
      '.asdk-label{display:block;font-size:13px;color:#334155;margin-bottom:6px;font-weight:500;}',
      '.asdk-required{color:#dc2626;margin-right:2px;}',
      '.asdk-input{width:100%;box-sizing:border-box;border:1px solid #e2e8f0;border-radius:10px;',
      'padding:11px 12px;font-size:14px;color:#0f172a;outline:none;transition:border .2s;background:#fff;}',
      '.asdk-input:focus{border-color:#4f46e5;}',
      '.asdk-textarea{width:100%;box-sizing:border-box;border:1px solid #e2e8f0;border-radius:10px;',
      'padding:11px 12px;font-size:14px;color:#0f172a;outline:none;transition:border .2s;background:#fff;',
      'resize:vertical;min-height:72px;font-family:inherit;line-height:1.5;}',
      '.asdk-textarea:focus{border-color:#4f46e5;}',
      '.asdk-code-row{display:flex;gap:8px;}',
      '.asdk-code-row .asdk-input{flex:1;min-width:0;}',
      '.asdk-code-btn{border:1px solid #4f46e5;background:#fff;color:#4f46e5;font-size:13px;font-weight:500;',
      'padding:0 14px;border-radius:10px;cursor:pointer;white-space:nowrap;transition:all .2s;}',
      '.asdk-code-btn:hover:not(:disabled){background:#eef2ff;}',
      '.asdk-code-btn:disabled{border-color:#c7d2fe;color:#94a3b8;cursor:not-allowed;}',
      '.asdk-btn{width:100%;border:0;background:#4f46e5;color:#fff;font-size:14px;font-weight:600;',
      'padding:12px 0;border-radius:10px;cursor:pointer;margin-top:6px;transition:background .2s;}',
      '.asdk-btn:hover{background:#4338ca;}',
      '.asdk-btn:disabled{background:#a5b4fc;cursor:not-allowed;}',
      '.asdk-msg{min-height:20px;font-size:12px;margin:4px 0 8px;text-align:center;}',
      '.asdk-msg.error{color:#dc2626;}',
      '.asdk-msg.ok{color:#059669;}',
      '.asdk-tip{font-size:12px;color:#94a3b8;text-align:center;margin:14px 0 0;line-height:1.6;}'
    ].join('');

    var style = el('style', { text: css });
    // 样式节点挂到卡片内，随弹窗一起销毁

    /* --- 结构 --- */
    // 登录图标：盾牌轮廓 + 钥匙孔（寓意"安全登录/授权"）
    var logoSvg =
      '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">' +
      '<path d="M12 2.5L4.5 5.4v5.1c0 4.6 3.2 8.9 7.5 10.5 4.3-1.6 7.5-5.9 7.5-10.5V5.4L12 2.5z"' +
      ' stroke="#fff" stroke-width="1.8" stroke-linejoin="round" fill="none"/>' +
      '<circle cx="12" cy="10" r="2.2" fill="#fff"/>' +
      '<path d="M12 12.2v3.8" stroke="#fff" stroke-width="1.8" stroke-linecap="round"/>' +
      '</svg>';
    var logo = el('div', { class: 'asdk-logo' });
    logo.innerHTML = logoSvg;
    var footerTip; // 底部提示（仅登录页显示）

    var title = el('p', { class: 'asdk-title', text: '登录授权' });
    var sub = el('p', { class: 'asdk-sub', text: '使用邮箱与验证码登录后继续访问' });

    var tabLogin = el('button', { class: 'asdk-tab active', type: 'button', text: '登录' });
    var tabApply = el('button', { class: 'asdk-tab', type: 'button', text: '申请访问权限' });
    var tabs = el('div', { class: 'asdk-tabs' }, [tabLogin, tabApply]);

    // 登录面板
    var loginEmail = el('input', { class: 'asdk-input', type: 'email', placeholder: '请输入邮箱', autocomplete: 'email' });
    var loginCode = el('input', { class: 'asdk-input', type: 'text', placeholder: '请输入验证码', maxlength: '6' });
    var getCodeBtn = el('button', { class: 'asdk-code-btn', type: 'button', text: '获取验证码' });
    var loginMsg = el('p', { class: 'asdk-msg' });
    var loginBtn = el('button', { class: 'asdk-btn', type: 'button', text: '登 录' });
    var loginPanel = el('div', {}, [
      el('div', { class: 'asdk-field' }, [el('label', { class: 'asdk-label', text: '邮箱' }), loginEmail]),
      el('div', { class: 'asdk-field' }, [
        el('label', { class: 'asdk-label', text: '验证码' }),
        el('div', { class: 'asdk-code-row' }, [loginCode, getCodeBtn])
      ]),
      loginMsg, loginBtn
    ]);

    // 申请面板
    var applyName = el('input', { class: 'asdk-input', type: 'text', placeholder: '请输入申请人姓名', autocomplete: 'name' });
    var applyPhone = el('input', { class: 'asdk-input', type: 'tel', placeholder: '请输入手机号', maxlength: '11', autocomplete: 'tel' });
    var applyEmail = el('input', { class: 'asdk-input', type: 'email', placeholder: '请输入邮箱', autocomplete: 'email' });
    var applyReason = el('textarea', { class: 'asdk-textarea', rows: '3', placeholder: '请输入申请原因', maxlength: '200' });
    var applyMsg = el('p', { class: 'asdk-msg' });
    var applyBtn = el('button', { class: 'asdk-btn', type: 'button', text: '申请体验' });
    // 生成带红色必填星号的 label
    function reqLabel(text) {
      var lb = el('label', { class: 'asdk-label' });
      lb.appendChild(el('span', { class: 'asdk-required', text: '*' }));
      lb.appendChild(document.createTextNode(' ' + text));
      return lb;
    }

    var applyPanel = el('div', { style: 'display:none;' }, [
      el('div', { class: 'asdk-field' }, [reqLabel('名称'), applyName]),
      el('div', { class: 'asdk-field' }, [reqLabel('电话'), applyPhone]),
      el('div', { class: 'asdk-field' }, [reqLabel('邮箱'), applyEmail]),
      el('div', { class: 'asdk-field' }, [reqLabel('申请原因'), applyReason]),
      applyMsg, applyBtn,
      el('p', { class: 'asdk-tip', text: '审核结果将发送至您的邮箱' })
    ]);

    var card = el('div', { class: 'asdk-card' }, [
      style, logo, title, sub, tabs, loginPanel, applyPanel,
      footerTip = el('p', { class: 'asdk-tip', text: '登录后方可使用' })
    ]);
    var overlay = el('div', { class: 'asdk-overlay' }, [card]);

    /* --- 交互逻辑 --- */
    function switchTab(isLogin) {
      tabLogin.className = 'asdk-tab' + (isLogin ? ' active' : '');
      tabApply.className = 'asdk-tab' + (isLogin ? '' : ' active');
      loginPanel.style.display = isLogin ? '' : 'none';
      applyPanel.style.display = isLogin ? 'none' : '';
      // 「登录后方可使用」提示仅在登录页显示，申请体验页隐藏
      footerTip.style.display = isLogin ? '' : 'none';
    }
    tabLogin.addEventListener('click', function () { switchTab(true); });
    tabApply.addEventListener('click', function () { switchTab(false); });

    function setMsg(node, text, ok) {
      node.textContent = text || '';
      node.className = 'asdk-msg' + (text ? (ok ? ' ok' : ' error') : '');
    }

    // 过期/异常场景重新弹窗时，展示待显示提示（如“登录已过期，请重新登录”）
    if (self._pendingMsg) {
      setMsg(loginMsg, self._pendingMsg, false);
      self._pendingMsg = '';
    }

    // 获取验证码（登录面板内）：校验邮箱 -> 调接口 -> 60秒倒计时
    var countdown = 0;
    function startCountdown(sec) {
      countdown = sec;
      getCodeBtn.disabled = true;
      getCodeBtn.textContent = countdown + 's后重发';
      if (self._countdownTimer) clearInterval(self._countdownTimer);
      self._countdownTimer = setInterval(function () {
        countdown--;
        if (countdown <= 0) {
          clearInterval(self._countdownTimer);
          self._countdownTimer = null;
          getCodeBtn.disabled = false;
          getCodeBtn.textContent = '获取验证码';
        } else {
          getCodeBtn.textContent = countdown + 's后重发';
        }
      }, 1000);
    }
    getCodeBtn.addEventListener('click', function () {
      var email = loginEmail.value.trim();
      if (!isValidEmail(email)) return setMsg(loginMsg, '请先输入正确的邮箱地址', false);
      getCodeBtn.disabled = true;
      getCodeBtn.textContent = '发送中…';
      // 获取动态验证码仅需邮箱（后端按邮箱发送验证码）
      self.sendCode(email)
        .then(function (json) {
          var mockCode = json.data && json.data.code;
          setMsg(loginMsg, mockCode
            ? '验证码已发送：' + mockCode
            : (json.message || '验证码已发送至您的邮箱'), true);
          if (mockCode) loginCode.value = mockCode; // 演示环境：mock 回填
          startCountdown(60);
        })
        .catch(function (err) {
          setMsg(loginMsg, (err && err.message) || '获取验证码失败，请重试', false);
          getCodeBtn.disabled = false;
          getCodeBtn.textContent = '获取验证码';
        });
    });

    // 登录
    loginBtn.addEventListener('click', function () {
      var email = loginEmail.value.trim();
      var code = loginCode.value.trim();
      if (!isValidEmail(email)) return setMsg(loginMsg, '请输入正确的邮箱地址', false);
      if (!code) return setMsg(loginMsg, '请输入验证码', false);
      loginBtn.disabled = true;
      loginBtn.textContent = '登录中…';
      var api = self._config.useMock ? '__login__' : self._config.loginApi;
      self._post(api, { email: email, code: code })
        .then(function (json) {
          // 成功返回（顶层结构）：
          // { message:"登录成功", financeToken:"...", username:"张三", email:"...", expires_in:1800 }
          // 无 error 字段即成功
          var data = json.data || json;
          var financeToken = data.financeToken || '';
          if (!financeToken) return setMsg(loginMsg, '登录成功但未返回 financeToken，请联系管理员', false);
          self._onLoginSuccess({
            email: data.email || email,
            financeToken: financeToken,
            username: data.username || '',
            expires_in: data.expires_in || 0
          });
          loginBtn.disabled = false;
          loginBtn.textContent = '登 录';
        })
        .catch(function (err) {
          setMsg(loginMsg, (err && err.message) || '登录失败，请重试', false);
          loginBtn.disabled = false;
          loginBtn.textContent = '登 录';
        });
    });

    // 申请体验
    applyBtn.addEventListener('click', function () {
      var username = applyName.value.trim();
      var phone = applyPhone.value.trim();
      var email = applyEmail.value.trim();
      var reason = applyReason.value.trim();
      if (!username) return setMsg(applyMsg, '请输入申请人姓名', false);
      if (!isValidPhone(phone)) return setMsg(applyMsg, '请输入正确的手机号', false);
      if (!isValidEmail(email)) return setMsg(applyMsg, '请输入正确的邮箱地址', false);
      if (!reason) return setMsg(applyMsg, '请输入申请原因', false);
      applyBtn.disabled = true;
      applyBtn.textContent = '申请中…';
      self.applyCode(email, username, phone, reason)
        .then(function (json) {
          var mockCode = json.data && json.data.code;
          // 优先展示后端返回的 message，无则使用默认文案
          setMsg(applyMsg, mockCode
            ? '申请成功！验证码：' + mockCode + '（已自动填入）'
            : (json.message || '申请成功，请查收邮箱'), true);
          // 演示环境：自动切回登录并填入
          if (mockCode) {
            loginEmail.value = email;
            loginCode.value = mockCode;
            setTimeout(function () { switchTab(true); }, 1200);
          }
          applyBtn.disabled = false;
          applyBtn.textContent = '申请体验';
        })
        .catch(function (err) {
          setMsg(applyMsg, (err && err.message) || '申请失败，请重试', false);
          applyBtn.disabled = false;
          applyBtn.textContent = '申请体验';
        });
    });

    // 回车提交（textarea 中回车为换行，不触发提交）
    [loginEmail, loginCode].forEach(function (i) {
      i.addEventListener('keydown', function (e) { if (e.key === 'Enter') loginBtn.click(); });
    });
    [applyName, applyPhone, applyEmail].forEach(function (i) {
      i.addEventListener('keydown', function (e) { if (e.key === 'Enter') applyBtn.click(); });
    });

    /* --- 防绕过：阻止遮罩层上的任何点击穿透 / 拖拽 --- */
    overlay.addEventListener('mousedown', function (e) { e.stopPropagation(); });
    overlay.addEventListener('mouseup', function (e) { e.stopPropagation(); });

    return overlay;
  };

  /* ---------------- 页面锁定与防绕过 ---------------- */

  // 锁定页面滚动，避免弹窗下方内容被操作
  AuthSDK.prototype._lockPage = function () {
    document.documentElement.style.overflow = 'hidden';
    document.body.style.overflow = 'hidden';
  };

  AuthSDK.prototype._unlockPage = function () {
    document.documentElement.style.overflow = '';
    document.body.style.overflow = '';
  };

  // 拦截 ESC / 关闭手势；若用户尝试移除弹窗 DOM 则自动恢复
  AuthSDK.prototype._startProtect = function () {
    var self = this;

    // 1) 拦截键盘 ESC / F5 以外的关闭类按键
    this._keyHandler = function (e) {
      if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); }
    };
    document.addEventListener('keydown', this._keyHandler, true);

    // 2) MutationObserver：弹窗被删除或被隐藏时立即恢复
    this._observer = new MutationObserver(function () {
      if (!self._modalVisible) return;
      var ov = self._overlay;
      if (!ov || !document.body.contains(ov)) {
        // 弹窗 DOM 被移除（如通过 DevTools），重新挂载
        document.body.appendChild(ov);
      } else {
        // 弹窗被隐藏 / 样式被篡改，恢复可见
        var st = getComputedStyle(ov);
        if (st.display === 'none' || st.visibility === 'hidden' || Number(st.opacity) === 0) {
          ov.style.setProperty('display', 'flex', 'important');
          ov.style.setProperty('visibility', 'visible', 'important');
          ov.style.setProperty('opacity', '1', 'important');
        }
      }
    });
    this._observer.observe(document.body, { childList: true, subtree: false });
    this._observer.observe(this._overlay, {
      attributes: true,
      attributeFilter: ['style', 'class', 'hidden']
    });
  };

  AuthSDK.prototype._destroyModal = function () {
    this._modalVisible = false;
    if (this._countdownTimer) { clearInterval(this._countdownTimer); this._countdownTimer = null; }
    if (this._observer) { this._observer.disconnect(); this._observer = null; }
    if (this._keyHandler) {
      document.removeEventListener('keydown', this._keyHandler, true);
      this._keyHandler = null;
    }
    if (this._overlay && this._overlay.parentNode) {
      this._overlay.parentNode.removeChild(this._overlay);
    }
    this._overlay = null;
    this._unlockPage();
  };

  /* ---------------- 导出 ---------------- */

  global.AuthSDK = new AuthSDK();
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = global.AuthSDK;
  }

  /**
   * 自动初始化兜底：接入方只引入 <script src="auth-sdk.js">（未显式调用 init）时，
   * 以内置默认配置自动启动登录校验，实现零配置接入。
   * 若业务方在 DOMContentLoaded 前已显式调用 init(自定义配置)，则不会重复初始化。
   */
  if (global.document && typeof global.document.addEventListener === 'function') {
    if (global.document.readyState === 'loading') {
      global.document.addEventListener('DOMContentLoaded', function () {
        if (!global.AuthSDK._inited) global.AuthSDK.init();
      });
    } else {
      // 异步引入等已错过 DOMContentLoaded 的场景，尽快初始化
      setTimeout(function () {
        if (!global.AuthSDK._inited) global.AuthSDK.init();
      }, 0);
    }
  }
})(typeof window !== 'undefined' ? window : this);
