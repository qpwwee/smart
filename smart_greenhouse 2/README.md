# 🌿 智能温室监控系统

原生桌面应用，双击即运行，无需浏览器。

## 快速获取 Windows .exe（无需本地构建）

把源码上传到 GitHub，自动编译出 Windows 和 Mac 版本：

**3 步搞定：**
1. 打开 https://github.com/new → 创建一个新仓库
2. 把本文件夹所有文件上传到那个仓库（直接拖进去）
3. 点 **Actions** 标签 → 左侧 **"打包 SmartGreenhouse"** → 右侧 **"Run workflow"**

等 3~5 分钟，Actions 运行完成后，页面下方会出现：
- **SmartGreenhouse-Windows** → 下载 `SmartGreenhouse.exe`，双击运行
- **SmartGreenhouse-Mac** → 下载 `SmartGreenhouse.app`，双击运行

以后再更新代码，只要 `git push` 就会自动重新打包。

## 手动本地构建

### Mac
```bash
bash build_mac.sh
```

### Windows
双击 `build_windows.bat`（需先安装 Python）
