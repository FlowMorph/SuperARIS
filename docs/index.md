# SuperARIS 文档入口

**从工作台理解角色、从上下文理解恢复、从用量文档理解本地统计。** 以下入口按任务主题导航。

1. 工作台、原生会话与输入归属：[[docs/WORKBENCH|工作台]]，命令入口 [[src/superaris/cli.py|CLI]]，绑定与恢复 [[src/superaris/runtime.py|runtime]]。
2. ARIS技能、项目上下文与恢复指针：[[docs/PROJECT_CONTEXT|上下文]]，实现 [[src/superaris/context.py|context]]。
3. 结果句柄、投递与项目记忆：[[docs/RESULTS_AND_MEMORY|结果与记忆]]，实现 [[src/superaris/tasks.py|tasks]]、[[src/superaris/bridge.py|bridge]]。
4. 可选本地用量、角色归属与未知边界：[[docs/USAGE|用量检测]]，汇总入口 [[src/superaris/usage.py|usage]]。
5. ARIS资源与依赖：[[docs/DEPENDENCIES|依赖]]；Windows安装与支持范围：[[docs/WINDOWS|Windows]]。
