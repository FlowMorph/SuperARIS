# SuperARIS 文档入口

**从工作台理解角色、从上下文理解恢复、从用量文档理解本地统计。** 以下入口按任务主题导航。

1. 工作台、原生会话与输入归属：[工作台](WORKBENCH.md)，命令入口 [CLI](../src/superaris/cli.py)，绑定与恢复 [runtime](../src/superaris/runtime.py)。
2. ARIS技能、项目上下文与恢复指针：[上下文](PROJECT_CONTEXT.md)，实现 [context](../src/superaris/context.py)。
3. 结果句柄、投递与项目记忆：[结果与记忆](RESULTS_AND_MEMORY.md)，实现 [tasks](../src/superaris/tasks.py)、[bridge](../src/superaris/bridge.py)。
4. 可选本地用量、角色归属与未知边界：[用量检测](USAGE.md)，汇总入口 [usage](../src/superaris/usage.py)。
5. ARIS资源与依赖：[依赖](DEPENDENCIES.md)；Windows安装与支持范围：[Windows](WINDOWS.md)。
