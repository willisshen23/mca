<!--
 * @Author: w60059030
 * @Date: 2026-09-07 15:57:15
 * @LastEditors: w60059030
 * @LastEditTime: 2026-09-07 16:03:21
 * @FilePath: \undefinedd:\DEMO\登录授权\接入登录sdk指南.md
 * @Description: 
-->
# 接入登录 SDK 指南

## 前置条件

- 新的sdk登录通过源码接入，然后再打镜像包
- auth-sdk.js在目录中
- index.html 是接入示例

---

## 操作步骤

### 1. 在本地开发的index.html中引入auth-sdk.js

```bash 
# index.html
<script src="auth-sdk.js?v=15"></script>
  <script>
    AuthSDK.init({
      // 申请体验码（申请Tab）：POST { email, username }
      applyApi: '/activity/authApi/login',
      // 获取动态体验码（登录面板按钮）：POST { email } -> { "message": "验证码已发送至您的邮箱" }
      codeApi: '/activity/authApi/register/send_code',
      // 体验码登录：POST { email, code }
      // 成功返回：{ message, financeToken, username, email, expires_in }，financeToken 存入 localStorage["financeToken"]
      loginApi: '/activity/authApi/register',
      // 登录态校验：页面 URL 带 ?financeToken=xxx 时自动调用
      // GET checkLoginApi?financeToken=xxx -> { valid, email, username, expires_at }
      // valid 为 true 时保存 financeToken 并放行页面；false 则弹出登录弹窗
      checkLoginApi: '/activity/authApi/check_login'
    });
  </script>
```

### 2. 重新打镜像包
