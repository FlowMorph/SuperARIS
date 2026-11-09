/* Content variants share the original seven-scene renderer and clock. */
(function () {
  const bi=(zh,en)=>({zh,en});
  const item=(type,at,values)=>({type,at,...values});
  const command=(at,zh,en)=>item('cmd',at,{text:bi(zh,en)});
  const info=(at,zh,en)=>item('info',at,{text:bi(zh,en)});
  const tool=(at,name,zh,en)=>item('tool',at,{name,sub:bi(zh,en)});
  const notice=(zh,en)=>({type:'notice',text:bi(zh,en)});
  const open=(at,zh,en)=>item('open',at,{text:bi(zh,en)});
  window.OrcaTeamModes={
    build:function(single,record) {
      const multi=JSON.parse(JSON.stringify(single));
      const s=multi;
      s[0].caption=bi('1. 选择 Claude Code 主控、Codex 工程与 Gemini 讨论写作，进入 Orca 三终端团队','1. Choose Claude Code lead, Codex engineering, and Gemini discussion & writing in Orca');
      const wizard=s[0].panes.main.steps.find(x=>x.type==='wizard');
      wizard.rows.zh[2]=['客户端组合','Claude Code / Codex / Gemini（AGY）'];
      wizard.rows.en[2]=['Team Preset','Claude Code / Codex / Gemini (AGY)'];
      s[0].panes.main.steps[2]=tool(1150,'Launch(Claude Code / Codex / Antigravity · terminal)', '已建立三个角色，分别读取 ARIS 导航与项目上下文','Three roles read their ARIS navigation and project context');
      s[0].panes.writer.steps[0].sub=bi('Gemini 负责想法讨论、论证组织与正文，独占 outputs/writer','Gemini discusses ideas, shapes arguments and writes prose in outputs/writer');

      s[1].caption=bi('2. CC 明确目标与门槛，Gemini 与你讨论怎样把结果组织成论证','2. CC fixes the goal and checks; discuss the argument with Gemini');
      s[1].focusedPane='writer';
      s[1].badges={main:'planning',eng:'ready',writer:'discussing'};
      s[1].inputs={main:'',engineer:'',writer:bi('这组结果应怎样组织成一段有说服力的论证？','How should we turn these results into a convincing argument?')};
      s[1].panes.main={history:[],steps:[
        tool(120,'Read(project-agent/SKILL.md, CURRENT.md, observations.csv)','目标：先核对 6 条记录，再写结果段；独立审阅后衔接补充计划','Goal: verify six records, then draft prose, obtain independent review, and plan follow-up'),
        info(650,'CC：工程负责可复算事实，Gemini 负责解释结构，我负责验收与下一步。','CC: engineering owns reproducible facts; Gemini owns the argument; I own acceptance and next steps.')
      ]};
      s[1].panes.writer={history:[],steps:[
        command(100,'这组结果应怎样组织成一段有说服力的论证？','How should we turn these results into a convincing argument?'),
        tool(380,'Read(paper-plan/SKILL.md, CURRENT.md)','先讨论论点与证据如何衔接，结果数字等待工程核查','Discuss claims and evidence first; wait for engineering to verify the numbers'),
        info(800,'Gemini：先交代对比口径，再写观测差异，最后提出待验证的机制。把结果和解释分开，读者更容易跟上论证。','Gemini: establish the comparison, state the observed difference, then propose a mechanism to test. Separate results from explanation so the argument is easy to follow.'),
        item('file',1350,{head:'outputs/writer/ARGUMENT.md',meta:'discussion → outline',body:bi('+ 口径：A、B 两组，各 3 条记录\n+ 结果：核实后再引用均值差\n+ 解释：作为补充消融要检验的假设','+ Comparison: groups A and B, three records each\n+ Result: cite the mean shift only after verification\n+ Explanation: a hypothesis for follow-up ablations')})
      ]};
      s[2].panes.writer={history:[],steps:[info(700,'Gemini 的 ARGUMENT.md 已保存；等待已核实数字，再将提纲展开成正文。','Gemini saved ARGUMENT.md; verified numbers will turn this outline into prose.')]};
      s[2].badges.writer='outline ready';

      s[3].caption=bi('4. 工程交付到达；打开交付，CC 独立复算后验收','4. Engineering delivers; open the delivery and let CC independently verify it');
      s[3].panes.main.history.push(notice('项目有新交付 · report.json 与 FACTS.md','New project delivery · report.json and FACTS.md'));
      s[3].inputs.main=bi('打开工程交付并继续：复算原始数据，核对报告后再交给写作。','Open the engineering delivery and continue: recompute the source data before handing it to the writer.');
      s[3].panes.main.steps[0]=open(0,'用户打开交付 · 继续核对','User opens the delivery · continue verification');
      s[3].panes.main.steps.splice(1,0,tool(200,'Read(NOTICES.md, report.json, FACTS.md)','读回真实文件，再核对 6 条原始数据','Read the delivered files, then verify all six source records'));
      s[3].panes.writer.steps=[info(920,'提纲已有：先写对比口径，再写差异；等待 CC 验收后的写作任务。','Outline ready: comparison first, then the difference; awaiting CC’s verified writing packet.')];

      s[4].caption=bi('5. 打开已验收事实，Gemini 沿讨论提纲组织论证并主写结果段','5. Open the verified facts; Gemini develops the argument and writes the results paragraph');
      s[4].inputs.writer=bi('打开写作交付并继续：沿 ARGUMENT.md 的思路，将已验收事实展开为结果段。','Open the writing packet and continue: develop ARGUMENT.md into a results paragraph using the verified facts.');
      s[4].panes.writer={history:[notice('写作任务已准备 · VERIFY_LOG.txt + FACTS.md + ARGUMENT.md','Writing packet ready · VERIFY_LOG.txt + FACTS.md + ARGUMENT.md')],steps:[
        open(0,'用户打开任务包 · 与 Gemini 继续写作','User opens the packet · continue writing with Gemini'),
        tool(300,'Read(paper-write/SKILL.md, ARGUMENT.md, VERIFY_LOG.txt, FACTS.md)','将“对比口径 → 观测 → 解释假设”连成正文，不只改写措辞','Develop the comparison → observation → explanatory hypothesis into substantive prose'),
        item('file',1000,{head:'outputs/writer/results.tex',meta:'Gemini · substantive draft',body:bi('+ 在该消融样例中，B 的均值为 7.0，A 为 6.0，差值为 1.0。\n+ 我们将这一观测作为机制讨论的起点，并以补充消融检验其解释。','+ In this ablation example, B averages 7.0 versus 6.0 for A, a difference of 1.0.\n+ This observation motivates a mechanism discussion, whose explanation will be tested with follow-up ablations.')})
      ]};
      s[4].panes.main.steps[0].sub=bi('已准备给原 Gemini 会话的写作任务包；打开后沿原讨论继续','Writing packet prepared for the original Gemini session; open it to continue the discussion');

      s[5].caption=bi('6. 后台独立审阅，打开意见继续修订；CC 核对后签收','6. Independent background review; open its feedback, revise with Gemini, then CC accepts');
      s[5].inputs={main:'',engineer:'',writer:''};
      s[5].panes.main={history:[notice('Gemini 交付 results.tex · 待主控核查','Gemini delivered results.tex · awaiting lead verification')],steps:[
        open(100,'用户打开写作交付 · 继续审阅','User opens the writing delivery · continue review'),
        tool(400,'MCP(research-review · fresh context)','后台独立 reviewer 核对事实与论证，不增加常驻角色','A fresh background reviewer checks facts and argument; no extra resident role'),
        tool(2900,'Read(results.tex) → acknowledge(writer-round1)','CC 核对数字、来源与修订后的论证，再签收结果段','CC verifies the numbers, source and revised argument before accepting the prose')
      ]};
      s[5].panes.writer={history:[],steps:[
        item('notice',700,{text:bi('审阅意见已到 · 补上每组样本量与数据来源，区分观测与机制假设','Review ready · include per-group counts and data source; distinguish observation from mechanism')}),
        open(1100,'用户打开审阅意见 · Gemini 继续修订','User opens review feedback · Gemini continues revising'),
        tool(1500,'Update(outputs/writer/results.tex)','保留讨论主线，补齐每组 n=3 与来源，让每个论点都落到证据','Keep the argument, add n=3 per group and the source, and ground each claim in evidence'),
        item('file',2200,{head:'outputs/writer/results.tex',meta:'revised · evidence → argument',body:bi('+ observations.csv 含 6 条记录，A、B 各 3 条；均值分别为 6.0、7.0，观测差为 1.0。\n+ 该差异描述本样例的结果；机制解释作为后续消融计划要检验的假设。','+ observations.csv contains six records, three per group: means are 6.0 and 7.0, an observed difference of 1.0.\n+ This describes the example; the mechanism remains a hypothesis for the follow-up ablation plan.')})
      ]};
      s[5].reviewTitle=bi('后台独立 MCP 审阅 · 全新上下文','Background MCP review · fresh context');
      s[5].reviewBody=bi('补上每组样本量与数据来源，区分观测结论和机制假设。Gemini 沿原讨论修订，CC 验收。','Include per-group counts and source; separate observations from the mechanism hypothesis. Gemini revises; CC accepts.');
      s[6].caption=bi('7. 保存讨论、验收与下一步；回到项目，沿原团队继续','7. Save the discussion, acceptance and next step; return to the original team');
      s[6].panes.writer.steps[0].text=bi('Gemini 读回 ARGUMENT.md 与 results.tex，与你继续补充消融计划的讨论。','Gemini reads ARGUMENT.md and results.tex to continue discussing the follow-up plan with you.');
      const records=JSON.parse(JSON.stringify(record));
      records.zh[1]='2/7 讨论 · CC 持目标，Gemini 提出“口径 → 观测 → 假设”的论证结构';
      records.en[1]='2/7 Discuss · CC holds the goal; Gemini proposes comparison → observation → hypothesis';
      records.zh[3]='4/7 验收 · 打开工程交付，CC 独立复算并签收';
      records.en[3]='4/7 Verify · open engineering delivery; CC independently checks and accepts';
      records.zh[4]='5/7 主写 · 打开已验收事实，Gemini 沿原讨论写 results.tex';
      records.en[4]='5/7 Write · open verified facts; Gemini develops the argument in results.tex';
      records.zh[5]='6/7 修订 · 打开独立意见，Gemini 修订，CC 验收';
      records.en[5]='6/7 Revise · open independent feedback; Gemini revises, CC accepts';
      return {scenes:multi,records};
    }
  };
})();
