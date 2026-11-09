"""Small Simplified Chinese/English vocabulary for the SuperARIS interface."""

language = "zh"

_EN = {
    '未知': 'unknown',
    '本地用量 / Usage': 'Local usage',
    '范围内本地观测；缺失字段为未知。': 'Local observations in range; missing fields are unknown.',
    '{label}：请求 {requests}，输入 {input}，缓存读 {read}，缓存写 {write}，输出 {output}，等效 {equivalent}，占比 {share}；状态 {status}': '{label}: requests {requests}, input {input}, cache read {read}, cache write {write}, output {output}, equivalent {equivalent}, share {share}; status {status}',
    "：": ": ",
    "主会话：统筹、恢复与验收": "Main: coordination, recovery and acceptance",
    "工程：实现与事实核查": "Engineering: implementation and fact checking",
    "写作：正文与解释": "Writing: prose and explanation",
    "主会话": "Main", "工程": "Engineer", "写作": "Writer", "工作台": "Workbench",
    "ARIS 工作包已准备": "ARIS work packet ready",
    "已取消启动，未创建工作台。": "Startup cancelled; no workbench was created.",
    "无法创建项目目录：{error}": "Cannot create project directory: {error}",
    "已保留当前工作台。下次在 superaris 中选择这个项目即可继续。": "The current workbench is preserved. Select this project in superaris next time to continue.",
    "工作台已准备：{project}\n已启动的角色保持原任务。": "Workbench ready: {project}\nStarted roles retain their original tasks.",
    "暂时无法启动工作台：{error}": "Cannot start the workbench yet: {error}",
    "Claude Code（CC）": "Claude Code (CC)", "Antigravity（AGY）": "Antigravity (AGY)",
    "仅 Codex（三角色）": "Codex only (three roles)",
    "CC + Codex（三角色）": "CC + Codex (three roles)",
    "CC + Codex + AGY（三角色）": "CC + Codex + AGY (three roles)",
    "请输入上面的选项编号；b 返回项目选择，q 取消。": "Enter an option number; b returns to project selection, q cancels.",
    "\n本机客户端命令：": "\nLocal client commands:",
    "已找到": "found", "未找到": "not found",
    "登录与模型设置由各自客户端处理；CC 使用你的已有配置。": "Each client handles its own login and model settings; CC uses your existing configuration.",
    "工作台宿主": "Workbench host", "Herdr（推荐）": "Herdr (recommended)",
    "宿主：{host}": "Host: {host}",
    "Orca：已找到 CLI；启动时核对原生服务，沿用你的模型与登录配置。": "Orca: CLI found; startup checks the native service and keeps your model and login configuration.",
    "Orca 应用已安装；请打开 Settings → General → Orca CLI 注册命令，再继续这个项目。": "Orca is installed; open Settings → General → Orca CLI to register its command, then resume this project.",
    "原项目 Orca CLI 入口不可用：{path}。请核对原入口，或用 --orca-bin 明确指定可用 CLI 后继续。": "The original project's Orca CLI is unavailable: {path}. Check the recorded entry, or explicitly select a working CLI with --orca-bin before resuming.",
    "Orca CLI 未找到；请从 https://www.onorca.dev/download 安装并打开 Orca，再继续这个项目。": "Orca CLI was not found; install and open Orca from https://www.onorca.dev/download, then resume this project.",
    "请在 Orca 中自行处理原生提示；处理后回到这里选择继续，原会话和选择保持不变。": "Handle the native prompt in Orca, then return here to continue. The original sessions and selections stay unchanged.",
    "已处理原生提示，继续": "Native prompt handled; continue",
    "Herdr：已找到，复用现有服务；需要时建立所选项目工作台。": "Herdr: found; reuse the existing service and create the selected project workbench when needed.",
    "Herdr：未找到；确认启动后会使用官方 Windows 安装器。": "Herdr: not found; confirmed startup will use the official Windows installer.",
    "Herdr：未找到；选择启动后会经现有 Homebrew 安装（brew install herdr）。": "Herdr: not found; starting will install it through existing Homebrew (brew install herdr).",
    "Herdr：未找到，也未找到 Homebrew。请先安装 Herdr TUI 后重试：": "Herdr and Homebrew were not found. Install Herdr TUI, then retry:",
    "https://herdr.dev/tui/docs/install/ （本次不会启动模型或创建项目）": "https://herdr.dev/tui/docs/install/ (No model will start and no project will be created.)",
    "\n{role} / {client} — 模型": "\n{role} / {client} — Model",
    "沿用已有设置": "Keep existing settings", "手动输入模型 ID": "Enter a model ID",
    "{title}（可选型号）": "{title} (optional model)", "模型选择": "Model selection", "模型 ID": "Model ID",
    "请输入原生 CLI 支持的模型 ID，或 b 返回项目选择。": "Enter a model ID supported by the native CLI, or b to return to project selection.",
    "\n分工与布局预览：": "\nRoles and layout preview:",
    "\nSuperARIS · 中文启动向导": "\nSuperARIS · Startup wizard",
    "逐步选择项目、客户端和模型，再预览启动。b 返回项目选择，q 随时取消。": "Choose a project, clients and models, then preview startup. b returns to project selection; q cancels at any time.",
    "当前位置：{path}": "Current directory: {path}",
    "当前位置是 Home 或文件系统根；建议使用独立项目目录，避免把整个目录作为写域。": "This is Home or the filesystem root; use a dedicated project directory to keep the write scope focused.",
    "\n[1/4] 选择项目": "\n[1/4] Choose a project",
    "项目目录（可输入新目录，含空格无需引号）": "Project directory (new paths allowed; spaces need no quotes)",
    "这个路径是文件，请选择一个项目目录。": "This path is a file. Choose a project directory.",
    "已有工作台记录不完整；请核对原项目记录，不会另建 owner。": "The existing workbench record is incomplete. Inspect the original project record; no new owner will be created.",
    "\n发现已有工作台：{name}（保留原负责人、模型、任务和布局）": "\nExisting workbench found: {name} (preserve its owners, models, tasks and layout)",
    "上次启动尚未完成，将继续原先选择的角色；已启动角色不重复派工。": "The previous startup is incomplete. Continue the originally selected roles without dispatching started roles again.",
    "原模型保持": "Original model preserved", "如何继续": "How to continue",
    "继续原工作台": "Resume existing workbench", "更换项目": "Choose another project", "取消": "Cancel",
    "\n[4/4] 恢复摘要": "\n[4/4] Recovery summary",
    "项目：{project}\n操作：继续原负责人和未完事项；保留任务、模型与现有窗口。": "Project: {project}\nAction: resume the original owners and pending work; preserve tasks, models and existing panes.",
    "请选择": "Choose an option", "启动（继续原工作台）": "Start (resume existing workbench)", "返回修改": "Back to edit",
    "待完成启动记录与当前项目不符": "The pending startup record does not match this project",
    "\n[2/4] 客户端组合与模型": "\n[2/4] Clients and models",
    "（缺少 {missing}，暂不可用）": " (missing {missing}; currently unavailable)",
    "当前组合均需要 Codex。请先安装缺失客户端并完成其原生登录，再运行 superaris。": "All current combinations require Codex. Install the missing clients and complete their native login before running superaris again.",
    "客户端组合": "Client combination",
    "请先安装该组合缺少的客户端并完成原生登录，或选择本机可用组合。": "Install the missing clients and complete their native login, or choose an available combination.",
    "\n[3/4] 分工与工作台": "\n[3/4] Roles and workbench", "工作台名称": "Workbench name",
    "当前填写的任务：{task}": "Current task: {task}", "任务安排": "Task setup",
    "保留当前任务": "Keep current task", "重新填写": "Enter a new task", "清空，进入后再给任务": "Clear task; provide it after entering",
    "新的任务（留空则进入后再给任务）": "New task (leave blank to provide after entering)",
    "本次任务（留空则进入后再给任务）": "Task (leave blank to provide after entering)",
    "\n[4/4] 启动摘要": "\n[4/4] Startup summary", "（启动时创建）": " (created at startup)",
    "项目：{project}{created}": "Project: {project}{created}", "工作台：SuperARIS · {name}": "Workbench: SuperARIS · {name}",
    "项目统筹与验收（协作者目录除外）": "Project coordination and acceptance (excluding collaborator directories)",
    "{scope}（独占）": "{scope} (exclusive)", "沿用 CLI 配置": "Keep CLI configuration",
    "任务：{task}": "Task: {task}", "暂不安排，进入后再告诉主会话": "Not assigned yet; tell the main role after entering",
    "将打开所选工作台，加载项目与 ARIS 技能，并接收协作者后续结果。": "Open the selected workbench, load project context and ARIS skills, and receive collaborators' later results.",
    "CC/AGY 收到后续结果时会提示你查看。": "CC/AGY will notify you when later results need your attention.",
    "启动": "Start", "\n返回项目选择；此前未启动会话或写入项目。": "\nReturning to project selection; no session has started and no project files have been written.",
    "无法读取这个项目：{error}。请重新选择，或 q 取消。": "Cannot read this project: {error}. Choose another project, or q to cancel.",
    "\n正在准备项目、ARIS 技能与所选角色…": "\nPreparing the project, ARIS skills and selected roles…",
    "SuperARIS 启动准备": "SuperARIS startup preparation",
    "请查看 {role} 窗格；原生提示由你处理，其他角色会继续准备。": "Check the {role} pane and handle its native prompt; other roles will continue preparing.",
    "仍需准备角色：{roles}。原选择已保留，请安装相应客户端后继续。": "Roles still need preparation: {roles}. Your selections are preserved; install the required clients, then continue.",
    "SuperARIS 启动未完成": "SuperARIS startup incomplete",
    "原会话和选择已保留。退出客户端后可查看启动错误并继续处理。": "The original sessions and selections are preserved. After leaving the client, inspect the startup error and continue.",
    "\n正在进入项目工作台；请自行处理原生提示。启动会在界面保持打开时继续。": "\nEntering the project workbench. Handle native prompts yourself; startup continues while the interface stays open.",
    "客户端仍在等待": "The client is still waiting", "返回工作台处理": "Return to the workbench",
    "结束向导，保留当前会话": "Finish wizard; preserve current sessions",
}


def set_language(value: str) -> None:
    global language
    if value not in {"zh", "en"}:
        raise ValueError(f"Unsupported interface language: {value}")
    language = value


def tr(key: str, *, lang: str | None = None, **values) -> str:
    text = _EN.get(key, key) if (lang or language) == "en" else key
    return text.format(**values) if values else text


def role_label(role: str, *, lang: str | None = None) -> str:
    label = {"main": "主会话：统筹、恢复与验收", "engineer": "工程：实现与事实核查", "writer": "写作：正文与解释"}.get(role, role)
    return tr(label, lang=lang)
