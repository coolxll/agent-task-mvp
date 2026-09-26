const zh = document.documentElement.lang.startsWith('zh');
const labels = {
  en: {
    board: 'Kanban Board', colTodo: 'To Do', colRunning: 'In Progress', colNeedsInput: 'Needs Input', colReview: 'Ready for Review', colDone: 'Done',
    emptyCol: 'No tasks', openNewTask: '+ New Task', viewDetail: 'Details', answerPrompt: 'Answer', refresh: 'Refresh',
    tasks: 'Tasks', running: 'Running', review: 'Review', setup: 'Setup',
    newTask: 'New Task', createRun: 'Create and Run', createProject: 'Create Project',
    createWorkspace: 'Create Workspace', createNode: 'Add Node', projects: 'Projects',
    nodes: 'Nodes', workspaces: 'Workspaces', project: 'Project', node: 'Node',
    workspace: 'Workspace', agent: 'Agent', title: 'Title', description: 'Description',
    criteria: 'Acceptance criteria', name: 'Name', repoUrl: 'Repository URL',
    sourcePath: 'Existing repository path on Runner', baseRef: 'Base branch / ref',
    gates: 'Gate commands, one per line', endpoint: 'Runner endpoint', token: 'Runner token',
    sourceKind: 'Source type', managed: 'Managed clone', existing: 'Existing directory',
    autoManaged: 'Managed clone (clone automatically if missing)',
    autoExisting: 'Project default repository path',
    projectHelp: 'Create a Project with a repository URL. The Runner clones it when a task first uses a managed Workspace. An existing remote path is optional.',
    workspaceHelp: 'Choose a saved Workspace for a Task, or choose automatic preparation. Every Run gets a separate Git worktree.',
    nodeHelp: 'Start the Runner and SSH port forward before adding the Node.',
    taskHelp: 'Select a Project, Node, and Workspace. Creating the Task starts a Run immediately.',
    needSetup: 'Add a Project and Node in Setup first.',
    noAgents: 'No runnable Agent is available on this Node.',
    logs: 'Logs', cancel: 'Cancel', cleanup: 'Cleanup', result: 'View result',
    summary: 'Agent summary', files: 'Changed files', gatesResult: 'Gate results',
    diff: 'Diff', approve: 'Accept delivery and keep branch', reject: 'Reject delivery and delete branch',
    rerun: 'Run again', run: 'Run', status: 'Status', branch: 'Branch',
    workspacePath: 'Run worktree', sourceRepo: 'Repository on Runner', exitCode: 'exit code',
    taskState: {TODO:'Todo',PENDING:'Pending',PROVISIONING:'Preparing workspace',RUNNING:'Running',VERIFYING:'Verifying',NEEDS_INPUT:'Needs your input',REVIEW:'Delivery acceptance',SUCCEEDED:'Accepted',DONE:'Done',FAILED:'Failed',CANCELLED:'Cancelled',REJECTED:'Rejected'},
  },
  zh: {
    board: '任务看板', colTodo: '待办 (To Do)', colRunning: '执行中 (In Progress)', colNeedsInput: '等待补充信息 (Blocked)', colReview: '待交付验收 (Review)', colDone: '已完成 (Done)',
    emptyCol: '暂无任务', openNewTask: '+ 新建任务', viewDetail: '查看详情', answerPrompt: '去回答', refresh: '刷新',
    tasks: '新建/列表', running: '执行流程', review: '交付验收', setup: '配置',
    newTask: '新建任务', createRun: '创建并运行', createProject: '创建项目',
    createWorkspace: '创建工作区', createNode: '添加节点', projects: '项目',
    nodes: '节点', workspaces: '工作区', project: '项目', node: '节点',
    workspace: '工作区', agent: 'Agent', title: '任务标题', description: '任务描述',
    criteria: '验收条件', name: '名称', repoUrl: 'Git 仓库 URL',
    sourcePath: 'Runner 上已有仓库的路径', baseRef: '基础分支或 ref',
    gates: '验证命令，每行一条', endpoint: 'Runner 连接地址', token: 'Runner token',
    sourceKind: '来源类型', managed: '系统管理的克隆', existing: '已有目录',
    autoManaged: '托管克隆（缺少时自动克隆）', autoExisting: '项目默认仓库路径',
    projectHelp: '输入仓库 URL 即可创建项目。首次选择托管工作区执行任务时，Runner 会自动克隆。已有远端路径是可选项。',
    workspaceHelp: '创建任务时可选择已有工作区，也可让系统自动准备。每次 Run 仍会创建独立的 Git worktree。',
    nodeHelp: '添加节点前，请先启动远端 Runner 和 Mac 上的 SSH 端口转发。',
    taskHelp: '选择项目、节点和工作区；点击创建后立即启动一次 Run。',
    needSetup: '请先在配置页添加项目和节点。',
    noAgents: '此节点没有可运行的 Agent。',
    logs: '查看日志', cancel: '取消', cleanup: '清理工作区', result: '查看结果',
    summary: 'Agent 总结', files: '变更文件', gatesResult: '验证结果',
    diff: '代码差异', approve: '验收通过并保留分支', reject: '拒绝交付并删除分支',
    rerun: '重新运行', run: '运行', status: '状态', branch: '任务分支',
    workspacePath: '本次运行的 worktree', sourceRepo: 'Runner 上的仓库', exitCode: '退出码',
    taskState: {TODO:'待办',PENDING:'等待中',PROVISIONING:'准备工作区',RUNNING:'运行中',VERIFYING:'验证中',NEEDS_INPUT:'等待你补充信息',REVIEW:'待交付验收',SUCCEEDED:'已验收',DONE:'已完成',FAILED:'失败',CANCELLED:'已取消',REJECTED:'已拒绝'},
  },
};
Object.assign(labels.en, {
  eventTimeline:'Event timeline',
  planner:'Planner', remotePlanner:'Plan on selected Node', managerPlanner:'Plan on Manager (requires model API)',
  directory:'Working directory / project', browse:'Choose folder…', requirement:'What would you like to build or fix?',
  taskHelp:'Choose a folder and machine, then describe your goal. The remote agent plans, implements, reviews and tests it.',
  needSetup:'Add a Node in Setup, then choose a Git folder or an existing Project.',
  plan:'Execution plan', codeReview:'Code review', acceptance:'Acceptance report', package:'Task package',
  delivery:'Delivery', deliveryLocal:'Merge into selected local folder after approval', deliveryBranch:'Keep branch on Manager', deliveryGithub:'Create GitHub PR and merge after approval',
  save:'Save settings', retryDelivery:'Retry delivery', approveMerge:'Approve and merge PR', approveLocal:'Approve and merge locally',
  imported:'Folder selected', dirty:'Uncommitted changes: commit them before submitting.',
  stages:'Execution stages', returned:'Result repository on Manager', passed:'Passed', blocked:'Needs changes',
  choose:'Use this folder', up:'Parent folder', close:'Close', open:'Open',
  question:'The agent needs your input to continue', answer:'Send answer and continue',
  acceptanceHelp:'Code review and tests run remotely. Approval merges the reviewed commit into the selected clean local folder, merges a GitHub PR, or keeps a result branch, according to project settings. Rejection closes any PR and cleans the remote worktree.',
});
Object.assign(labels.zh, {
  eventTimeline:'执行事件',
  planner:'规划位置', remotePlanner:'在所选远端机器规划', managerPlanner:'在 Manager 本地规划（需模型 API）',
  directory:'工作目录 / 项目', browse:'选择文件夹…', requirement:'描述你想完成的需求',
  taskHelp:'选择目录和机器，写下目标。远端 Agent 会规划、实现、评审、测试并生成验收报告。',
  needSetup:'请在配置页添加节点，然后选择一个 Git 文件夹或已有项目。',
  plan:'执行计划', codeReview:'代码评审', acceptance:'验收报告', package:'任务包',
  delivery:'交付方式', deliveryLocal:'验收后合并到所选本机目录', deliveryBranch:'取回 Mac 并保留分支', deliveryGithub:'创建 GitHub PR，验收后合并',
  save:'保存设置', retryDelivery:'重试交付', approveMerge:'验收通过并合并 PR', approveLocal:'验收通过并合并到本机',
  imported:'已选择目录', dirty:'目录有未提交改动：提交后才能运行。',
  stages:'执行阶段', returned:'Manager 上的结果仓库', passed:'通过', blocked:'需要修改',
  choose:'使用此文件夹', up:'上级目录', close:'关闭', open:'打开',
  question:'Agent 需要你补充信息才能继续', answer:'发送回答并继续执行',
  acceptanceHelp:'代码评审和测试由远端工作流自动完成。这里由你决定是否接受成果：根据项目交付方式，合并到所选本机目录、合并 GitHub PR，或保留 Manager 结果分支。拒绝会关闭已有 PR 并清理远端工作区。',
});
const L = labels[zh ? 'zh' : 'en'];
const t = key => L[key] || key;
const stateName = value => L.taskState[value] || value;
const stageName = value => {
  const names = zh ? {PLANNING:'调查与规划',CODE_REVIEW:'独立代码评审',TESTING:'执行测试',ACCEPTANCE:'验收检查'} : {};
  if (value?.startsWith('IMPLEMENTING_')) return (zh ? '实现步骤 ' : 'Implement step ') + value.split('_').pop();
  return names[value] || stateName(value);
};
const esc = value => String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
const errorName = value => {
  const s = String(value || '');
  if (!zh) return s;
  if (s.includes('source_path must be a Git repository root')) return '路径必须是远端 Git 仓库根目录：' + s;
  if (s.includes('Runner unavailable')) return '无法连接 Runner：' + s;
  if (s.includes('Git clone failed')) return '克隆仓库失败：' + s;
  if (s.includes('Git fetch failed')) return '更新仓库失败：' + s;
  if (s.includes('unauthorized')) return 'Runner token 无效：' + s;
  return s;
};
let current = 'board';
let selectedRun = null;
let eventStream = null;
let selectedDeliveryPending = false;

async function api(path, method = 'GET', body) {
  const response = await fetch('/api' + path, {
    method, headers: {'Content-Type': 'application/json'},
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await response.json();
  if (!response.ok) throw Error(data.error || String(response.status));
  return data;
}

async function load() {
  const [projects, nodes, workspaces, tasks, runs, agents] = await Promise.all(
    ['/projects','/nodes','/workspaces','/tasks','/runs','/agents'].map(path => api(path))
  );
  return {projects, nodes, workspaces, tasks, runs, agents};
}

function options(rows, label) {
  return rows.map(row => `<option value="${row.id}">${esc(label(row))}</option>`).join('');
}

function formData(form) { return Object.fromEntries(new FormData(form)); }

function bindAgentAvailability(nodeSelect, agentSelect, submitButton) {
  let requestId = 0;
  const baseDisabled = Boolean(submitButton?.disabled);
  async function refresh(preferred) {
    const currentRequest = ++requestId;
    agentSelect.disabled = true;
    if (submitButton) submitButton.disabled = true;
    try {
      const data = await api('/nodes/' + Number(nodeSelect.value) + '/agents');
      if (currentRequest !== requestId) return;
      const available = data.agents.filter(row => row.available);
      agentSelect.innerHTML = available.length
        ? available.map(row => `<option value="${esc(row.kind)}">${esc(row.kind)}</option>`).join('')
        : `<option value="">${esc(t('noAgents'))}</option>`;
      const selected = available.some(row => row.kind === preferred) ? preferred : data.default_kind;
      if (selected && available.some(row => row.kind === selected)) agentSelect.value = selected;
      agentSelect.disabled = !available.length;
      if (submitButton) submitButton.disabled = baseDisabled || !available.length;
    } catch (error) {
      if (currentRequest !== requestId) return;
      agentSelect.innerHTML = `<option value="">${esc(errorName(error.message))}</option>`;
    }
  }
  nodeSelect.addEventListener('change', () => refresh());
  refresh(agentSelect.value);
}

async function show(view = current) {
  current = view;
  document.querySelectorAll('nav button[data-view]').forEach(button => {
    button.classList.toggle('active', button.dataset.view === view);
  });
  try {
    const data = await load();
    const app = document.getElementById('app');
    if (view === 'setup') renderSetup(app, data);
    else if (view === 'tasks') renderTasks(app, data);
    else if (view === 'running') renderRunning(app, data);
    else if (view === 'review') renderReview(app, data);
    else renderBoard(app, data);
    if ((view === 'running' || view === 'review') && selectedRun) await details(selectedRun);
  } catch (error) {
    document.getElementById('app').innerHTML = `<section class="bad">${esc(errorName(error.message))}</section>`;
  }
}

function renderBoard(app, {projects, nodes, workspaces, tasks, runs, agents}) {
  const projectMap = Object.fromEntries(projects.map(x => [x.id, x]));
  const nodeMap = Object.fromEntries(nodes.map(x => [x.id, x]));

  const latestRunByTask = {};
  runs.forEach(r => {
    if (!latestRunByTask[r.task_id] || r.id > latestRunByTask[r.task_id].id) {
      latestRunByTask[r.task_id] = r;
    }
  });

  const cols = {
    todo: [],
    running: [],
    needsInput: [],
    review: [],
    done: [],
  };

  tasks.forEach(task => {
    const run = latestRunByTask[task.id];
    if (!run || task.status === 'TODO') {
      cols.todo.push({task, run});
    } else if (['PENDING', 'PROVISIONING', 'RUNNING', 'VERIFYING'].includes(run.status)) {
      cols.running.push({task, run});
    } else if (run.status === 'NEEDS_INPUT') {
      cols.needsInput.push({task, run});
    } else if (run.status === 'REVIEW') {
      cols.review.push({task, run});
    } else {
      cols.done.push({task, run});
    }
  });

  function renderCard({task, run}) {
    const pName = projectMap[task.project_id]?.name || 'Project #' + task.project_id;
    const nName = run ? (nodeMap[run.node_id]?.name || 'Node #' + run.node_id) : '';
    const statusClass = run ? (
      run.status === 'NEEDS_INPUT' ? 'card-needs-input' :
      run.status === 'REVIEW' ? 'card-review-border' :
      ['RUNNING','PROVISIONING','PENDING','VERIFYING'].includes(run.status) ? 'card-running' : ''
    ) : '';
    const stageBadge = run?.stage ? `<span class="badge badge-stage">${esc(stageName(run.stage))}</span>` : '';
    const statusBadge = run ? `<span class="badge ${run.status === 'NEEDS_INPUT' ? 'badge-blocked' : run.status === 'REVIEW' ? 'badge-review' : 'badge-node'}">${esc(stateName(run.status))}</span>` : `<span class="badge badge-done">${esc(stateName(task.status))}</span>`;
    const questionSnippet = run?.status === 'NEEDS_INPUT' && run.question ? `<p class="bad" style="font-size:12px;margin:3px 0;line-height:1.3"><strong>Q:</strong> ${esc(run.question.slice(0, 80))}${run.question.length > 80 ? '...' : ''}</p>` : '';
    const errorSnippet = run?.error ? `<p class="bad" style="font-size:12px;margin:2px 0">${esc(errorName(run.error).slice(0, 60))}</p>` : '';
    const descSnippet = task.description ? `<div class="card-desc">${esc(task.description)}</div>` : '';

    return `
      <div class="kanban-card ${statusClass}" data-card-task="${task.id}" ${run ? `data-card-run="${run.id}"` : ''}>
        <div class="card-top">
          <span class="card-id">#${task.id}</span>
          <span class="muted" style="max-width:140px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(pName)}</span>
        </div>
        <div class="card-title">${esc(task.title || task.description.slice(0, 50))}</div>
        ${descSnippet}
        ${questionSnippet}
        ${errorSnippet}
        <div class="card-tags">
          ${statusBadge}
          ${stageBadge}
          ${nName ? `<span class="badge badge-node">${esc(nName)} · ${esc(run.agent_kind || '')}</span>` : ''}
        </div>
        <div class="card-footer">
          <span class="muted">${esc((task.created_at || '').slice(11, 16))}</span>
          <div>
            ${run ? `<button type="button" class="card-btn" data-detail="${run.id}">${t('viewDetail')}</button>` : ''}
            ${run?.status === 'NEEDS_INPUT' ? `<button type="button" class="card-btn btn-primary" data-detail="${run.id}">${t('answerPrompt')}</button>` : ''}
            ${run?.status === 'REVIEW' ? `<button type="button" class="card-btn btn-primary" data-detail="${run.id}">${t('review')}</button>` : ''}
            ${['TODO','FAILED','REJECTED','CANCELLED'].includes(task.status) || (run && ['FAILED','CANCELLED'].includes(run.status)) ? `<button type="button" class="card-btn" data-rerun="${task.id}">${t('rerun')}</button>` : ''}
          </div>
        </div>
      </div>
    `;
  }

  function renderCol(colKey, title, items) {
    return `
      <div class="kanban-col" data-col="${colKey}">
        <div class="kanban-col-header">
          <span>${title}</span>
          <span class="kanban-count">${items.length}</span>
        </div>
        <div class="kanban-cards">
          ${items.length ? items.map(renderCard).join('') : `<div class="kanban-empty">${t('emptyCol')}</div>`}
        </div>
      </div>
    `;
  }

  app.innerHTML = `
    <div class="board-toolbar">
      <div><h2>${t('board')}</h2></div>
      <div>
        <button type="button" class="btn-primary" id="open-new-task">${t('openNewTask')}</button>
        <button type="button" id="refresh-board">${t('refresh')}</button>
      </div>
    </div>
    <div class="kanban-grid">
      ${renderCol('todo', t('colTodo'), cols.todo)}
      ${renderCol('running', t('colRunning'), cols.running)}
      ${renderCol('needsInput', t('colNeedsInput'), cols.needsInput)}
      ${renderCol('review', t('colReview'), cols.review)}
      ${renderCol('done', t('colDone'), cols.done)}
    </div>
    <dialog id="detail-modal">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
        <h2 style="margin:0">${t('viewDetail')}</h2>
        <button type="button" id="close-detail-modal">${t('close')}</button>
      </div>
      <div id="detail"></div>
    </dialog>
    <dialog id="new-task-dialog">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
        <h2 style="margin:0">${t('newTask')}</h2>
        <button type="button" id="close-new-task-dialog">${t('close')}</button>
      </div>
      <p class="muted">${t('taskHelp')}</p>
      ${(!projects.length || !nodes.length) ? `<p class="bad">${t('needSetup')}</p>` : ''}
      <form id="task-modal-form">
        <label>${t('directory')}<select name="project_id" id="modal-task-project" required>${options(projects, x => x.local_path || x.name + ' · ' + (x.repo_url || x.source_path))}</select></label>
        <button type="button" id="modal-browse-folder">${t('browse')}</button><span id="modal-folder-note" class="muted" style="margin-left:8px"></span>
        <label>${t('node')}<select name="node_id" id="modal-task-node" required>${options(nodes, x => x.name)}</select></label>
        <label>${t('agent')}<select name="agent_kind" id="modal-task-agent" required>${agents.map(kind => `<option value="${esc(kind)}">${esc(kind)}</option>`).join('')}</select></label>
        <label>${t('planner')}<select name="planner"><option value="remote">${t('remotePlanner')}</option><option value="manager">${t('managerPlanner')}</option></select></label>
        <label>${t('requirement')}<textarea name="requirement" rows="8" required placeholder="${zh ? '例如：为导出功能增加 CSV 格式，保留现有 JSON 行为，并补充测试。' : 'For example: add CSV export, preserve JSON behavior, and add tests.'}"></textarea></label>
        <div style="display:flex;justify-content:flex-end;gap:8px;margin-top:16px">
          <button type="button" id="cancel-new-task">${t('close')}</button>
          <button type="submit" class="btn-primary" ${(!projects.length || !nodes.length) ? 'disabled' : ''}>${t('createRun')}</button>
        </div>
      </form>
    </dialog>
  `;

  const taskDialog = document.getElementById('new-task-dialog');
  const detailModal = document.getElementById('detail-modal');
  bindAgentAvailability(document.getElementById('modal-task-node'),
    document.getElementById('modal-task-agent'), document.querySelector('#task-modal-form button[type=submit]'));

  document.getElementById('open-new-task').onclick = () => taskDialog.showModal();
  document.getElementById('close-new-task-dialog').onclick = () => taskDialog.close();
  document.getElementById('cancel-new-task').onclick = () => taskDialog.close();
  document.getElementById('refresh-board').onclick = () => show('board');

  document.getElementById('close-detail-modal').onclick = () => {
    detailModal.close();
    if (eventStream) { eventStream.close(); eventStream = null; }
    selectedRun = null;
    show('board');
  };
  detailModal.onclose = () => {
    if (eventStream) { eventStream.close(); eventStream = null; }
    selectedRun = null;
    show('board');
  };

  document.getElementById('modal-browse-folder').onclick = () => browseFolder(async project => {
    const requirement = document.querySelector('#task-modal-form [name=requirement]').value;
    const node = document.getElementById('modal-task-node').value;
    await show('board');
    const td = document.getElementById('new-task-dialog');
    td.showModal();
    document.getElementById('modal-task-project').value = project.id;
    document.getElementById('modal-task-node').value = node;
    document.getElementById('modal-task-node').dispatchEvent(new Event('change'));
    document.querySelector('#task-modal-form [name=requirement]').value = requirement;
    document.getElementById('modal-folder-note').textContent = project.dirty ? t('dirty') : project.local_path;
  });

  document.getElementById('task-modal-form').onsubmit = async event => {
    event.preventDefault();
    const body = formData(event.target);
    const button = event.target.querySelector('button[type=submit]');
    button.disabled = true;
    try {
      const result = await api('/submit', 'POST', {
        project_id: Number(body.project_id),
        node_id: Number(body.node_id),
        agent_kind: body.agent_kind,
        planner: body.planner,
        requirement: body.requirement,
      });
      taskDialog.close();
      selectedRun = result.id;
      await show('board');
      openDetailModal(result.id);
    } finally {
      button.disabled = false;
    }
  };

  document.querySelectorAll('[data-card-run]').forEach(card => {
    card.onclick = event => {
      if (event.target.tagName === 'BUTTON') return;
      openDetailModal(Number(card.dataset.cardRun));
    };
  });

  document.querySelectorAll('[data-detail]').forEach(button => {
    button.onclick = event => {
      event.stopPropagation();
      openDetailModal(Number(button.dataset.detail));
    };
  });

  document.querySelectorAll('[data-rerun]').forEach(button => {
    button.onclick = async event => {
      event.stopPropagation();
      const taskId = Number(button.dataset.rerun);
      const previous = runs.find(x => x.task_id === taskId);
      if (!previous) return;
      const result = await api('/runs', 'POST', {
        task_id: taskId,
        node_id: previous.node_id,
        agent_kind: previous.agent_kind,
      });
      selectedRun = result.id;
      await show('board');
      openDetailModal(result.id);
    };
  });
}

function openDetailModal(runId) {
  const detailModal = document.getElementById('detail-modal');
  if (detailModal) {
    if (!detailModal.open) detailModal.showModal();
    details(runId);
  } else {
    selectedRun = runId;
    show('running');
  }
}

function renderSetup(app, {projects, nodes, workspaces}) {
  const projectMap = Object.fromEntries(projects.map(x => [x.id, x]));
  const nodeMap = Object.fromEntries(nodes.map(x => [x.id, x]));
  app.innerHTML = `
    <section><h2>${t('projects')}</h2><p class="muted">${t('projectHelp')}</p>
      <table><tbody>${projects.map(x => `<tr><td>${esc(x.name)}</td><td>${esc(x.repo_url || x.source_path)}</td><td>${esc(x.base_ref)}</td></tr>`).join('')}</tbody></table>
      ${projects.map(x => `<details><summary>${esc(x.name)} · ${t('delivery')}</summary><form data-project-settings="${x.id}">
        <label>${t('delivery')}<select name="delivery">${x.local_path ? `<option value="local" ${x.delivery === 'local' ? 'selected' : ''}>${t('deliveryLocal')}</option>` : ''}<option value="branch" ${x.delivery === 'branch' ? 'selected' : ''}>${t('deliveryBranch')}</option><option value="github" ${x.delivery === 'github' ? 'selected' : ''}>${t('deliveryGithub')}</option></select></label>
        <label>${t('baseRef')}<input name="base_ref" value="${esc(x.base_ref)}" required></label>
        <label>${t('gates')}<textarea name="gates">${esc((x.gates || []).join('\n'))}</textarea></label>
        <button>${t('save')}</button></form></details>`).join('')}
      <h3>${t('createProject')}</h3><form id="project-form">
        <label>${t('name')}<input name="name" required></label>
        <label>${t('repoUrl')}<input name="repo_url" placeholder="https://github.com/owner/repo.git"></label>
        <label>${t('sourcePath')}<input name="source_path" placeholder="/workspace/repo"></label>
        <label>${t('baseRef')}<input name="base_ref" value="HEAD"></label>
        <label>${t('gates')}<textarea name="gates"></textarea></label>
        <button>${t('createProject')}</button></form></section>
    <section><h2>${t('nodes')}</h2><p class="muted">${t('nodeHelp')}</p>
      <table><tbody>${nodes.map(x => `<tr><td>${esc(x.name)}</td><td>${esc(x.endpoint)}</td></tr>`).join('')}</tbody></table>
      <h3>${t('createNode')}</h3><form id="node-form">
        <label>${t('name')}<input name="name" required></label>
        <label>${t('endpoint')}<input name="endpoint" placeholder="http://127.0.0.1:18766" required></label>
        <label>${t('token')}<input name="token" required></label>
        <button>${t('createNode')}</button></form></section>
    <section><h2>${t('workspaces')}</h2><p class="muted">${t('workspaceHelp')}</p>
      <table><tbody>${workspaces.map(x => `<tr><td>${esc(x.name)}</td><td>${esc(projectMap[x.project_id]?.name)}</td><td>${esc(nodeMap[x.node_id]?.name)}</td><td>${esc(x.source_kind === 'managed' ? t('managed') : t('existing'))}</td><td>${esc(x.source_path)}</td></tr>`).join('')}</tbody></table>
      <h3>${t('createWorkspace')}</h3><form id="workspace-form">
        <label>${t('project')}<select name="project_id" required>${options(projects, x => x.name)}</select></label>
        <label>${t('node')}<select name="node_id" required>${options(nodes, x => x.name)}</select></label>
        <label>${t('name')}<input name="name" placeholder="${t('managed')}"></label>
        <label>${t('sourceKind')}<select name="source_kind"><option value="managed">${t('managed')}</option><option value="existing">${t('existing')}</option></select></label>
        <label>${t('sourcePath')}<input name="source_path" placeholder="/workspace/repo"></label>
        <button>${t('createWorkspace')}</button></form></section>`;
  document.querySelectorAll('[data-project-settings]').forEach(form => form.onsubmit = async event => {
    event.preventDefault();
    const body = formData(form);
    body.gates = body.gates.split('\n').map(x=>x.trim()).filter(Boolean);
    await api('/projects/' + form.dataset.projectSettings + '/settings','POST',body);
    show('setup');
  });
  document.getElementById('project-form').onsubmit = async event => {
    event.preventDefault();
    const body = formData(event.target);
    body.gates = body.gates.split('\n').map(x => x.trim()).filter(Boolean);
    await api('/projects','POST',body);
    show('setup');
  };
  document.getElementById('node-form').onsubmit = async event => {
    event.preventDefault(); await api('/nodes','POST',formData(event.target)); show('setup');
  };
  document.getElementById('workspace-form').onsubmit = async event => {
    event.preventDefault();
    const body = formData(event.target);
    body.project_id = Number(body.project_id);
    body.node_id = Number(body.node_id);
    await api('/workspaces','POST',body);
    show('setup');
  };
}

async function browseFolder(onSelect, path = '') {
  const dialog = document.createElement('dialog');
  document.body.appendChild(dialog);
  dialog.showModal();
  async function navigate(next) {
    const data = await api('/folders' + (next ? '?path=' + encodeURIComponent(next) : ''));
    dialog.innerHTML = `<h2>${t('browse')}</h2><form id="folder-path-form"><input id="folder-path" value="${esc(data.path)}"><button>${t('open')}</button></form>
      <button id="folder-up">${t('up')}</button><button id="folder-use">${t('choose')}</button><button id="folder-close">${t('close')}</button>
      <div style="max-height:50vh;overflow:auto">${data.directories.map((d,i)=>`<p><button data-folder="${i}">${d.git ? '▣ ' : '▸ '}${esc(d.name)}</button></p>`).join('')}</div>`;
    dialog.querySelector('#folder-path-form').onsubmit = e => { e.preventDefault(); navigate(dialog.querySelector('#folder-path').value); };
    dialog.querySelector('#folder-up').onclick = () => navigate(data.parent);
    dialog.querySelector('#folder-close').onclick = () => dialog.close();
    dialog.querySelectorAll('[data-folder]').forEach(b => b.onclick = () => navigate(data.directories[Number(b.dataset.folder)].path));
    dialog.querySelector('#folder-use').onclick = async () => {
      const project = await api('/projects/import', 'POST', {path:data.path});
      dialog.close();
      await onSelect(project);
    };
  }
  dialog.onclose = () => dialog.remove();
  try { await navigate(path); } catch (e) { dialog.close(); throw e; }
}

function renderTasks(app, {projects, nodes, tasks, runs, agents}) {
  const projectMap = Object.fromEntries(projects.map(x => [x.id, x]));
  app.innerHTML = `
    <section><h2>${t('newTask')}</h2><p class="muted">${t('taskHelp')}</p>
      ${(!projects.length || !nodes.length) ? `<p>${t('needSetup')}</p>` : ''}
      <form id="task-form">
        <label>${t('directory')}<select name="project_id" id="task-project" required>${options(projects, x => x.local_path || x.name + ' · ' + (x.repo_url || x.source_path))}</select></label>
        <button type="button" id="browse-folder">${t('browse')}</button><p id="folder-note" class="muted"></p>
        <label>${t('node')}<select name="node_id" id="task-node" required>${options(nodes, x => x.name)}</select></label>
        <label>${t('agent')}<select name="agent_kind" id="task-agent" required>${agents.map(kind => `<option value="${esc(kind)}">${esc(kind)}</option>`).join('')}</select></label>
        <label>${t('planner')}<select name="planner"><option value="remote">${t('remotePlanner')}</option><option value="manager">${t('managerPlanner')}</option></select></label>
        <label>${t('requirement')}<textarea name="requirement" rows="10" required placeholder="${zh ? '例如：为导出功能增加 CSV 格式，保留现有 JSON 行为，并补充测试。' : 'For example: add CSV export, preserve JSON behavior, and add tests.'}"></textarea></label>
        <button ${(!projects.length || !nodes.length) ? 'disabled' : ''}>${t('createRun')}</button>
      </form></section>
    <section><h2>${t('tasks')}</h2><table><tbody>${tasks.map(task => `
      <tr><td>#${task.id} ${esc(task.title)}</td><td>${esc(projectMap[task.project_id]?.name)}</td>
      <td>${esc(stateName(task.status))}</td><td>${['TODO','FAILED','REJECTED','CANCELLED'].includes(task.status) ? `<button data-rerun="${task.id}">${t('rerun')}</button>` : ''}</td></tr>`).join('')}</tbody></table></section>`;
  bindAgentAvailability(document.getElementById('task-node'), document.getElementById('task-agent'),
    document.querySelector('#task-form button:not([type=button])'));
  document.getElementById('browse-folder').onclick = () => browseFolder(async project => {
    const requirement = document.querySelector('[name=requirement]').value;
    const node = document.getElementById('task-node').value;
    await show('tasks');
    document.getElementById('task-project').value = project.id;
    document.getElementById('task-node').value = node;
    document.getElementById('task-node').dispatchEvent(new Event('change'));
    document.querySelector('[name=requirement]').value = requirement;
    document.getElementById('folder-note').textContent = project.dirty ? t('dirty') : project.local_path;
  });
  document.getElementById('task-form').onsubmit = async event => {
    event.preventDefault();
    const body = formData(event.target);
    const button = event.target.querySelector('button:not([type=button])');
    button.disabled = true;
    try {
      const result = await api('/submit','POST', {project_id:Number(body.project_id), node_id:Number(body.node_id),
        agent_kind:body.agent_kind, planner:body.planner, requirement:body.requirement});
      selectedRun = result.id;
      await show('running');
    } finally { button.disabled = false; }
  };
  document.querySelectorAll('[data-rerun]').forEach(button => {
    button.onclick = async () => {
      const taskId = Number(button.dataset.rerun);
      const previous = runs.find(x => x.task_id === taskId);
      if (!previous) return;
      const result = await api('/runs','POST', {task_id:taskId, node_id:previous.node_id,
        agent_kind:previous.agent_kind});
      selectedRun = result.id;
      show('running');
    };
  });
}

function renderRunning(app, {runs, tasks, nodes}) {
  const taskMap = Object.fromEntries(tasks.map(x => [x.id,x]));
  const nodeMap = Object.fromEntries(nodes.map(x => [x.id,x]));
  const rows = runs.filter(x => ['PENDING','PROVISIONING','RUNNING','VERIFYING','NEEDS_INPUT','FAILED','CANCELLED'].includes(x.status));
  app.innerHTML = `<section><h2>${t('running')}</h2><table><tbody>${rows.map(run => `
    <tr><td>#${run.id} ${esc(taskMap[run.task_id]?.title)}</td><td>${esc(nodeMap[run.node_id]?.name)} · ${esc(run.agent_kind)}</td>
    <td>${esc(stageName(run.stage || run.status))} ${run.error ? `<span class="bad">${esc(errorName(run.error))}</span>` : ''}</td>
    <td><button data-detail="${run.id}">${t('logs')}</button>
    ${['PENDING','PROVISIONING','RUNNING','VERIFYING','NEEDS_INPUT'].includes(run.status) ? `<button data-cancel="${run.id}">${t('cancel')}</button>` : ''}
    ${['FAILED','CANCELLED'].includes(run.status) && !run.cleaned_at ? `<button data-cleanup="${run.id}">${t('cleanup')}</button>` : ''}</td></tr>`).join('')}</tbody></table></section><section id="detail"></section>`;
  wireRunButtons();
}

function renderReview(app, {runs, tasks}) {
  const taskMap = Object.fromEntries(tasks.map(x => [x.id,x]));
  const rows = runs.filter(x => ['REVIEW','SUCCEEDED','REJECTED'].includes(x.status));
  app.innerHTML = `<section><h2>${t('review')}</h2><p>${t('acceptanceHelp')}</p><table><tbody>${rows.map(run => `
    <tr><td>#${run.id} ${esc(taskMap[run.task_id]?.title)}</td><td>${esc(stateName(run.status))}</td>
    <td><button data-detail="${run.id}">${t('result')}</button></td></tr>`).join('')}</tbody></table></section><section id="detail"></section>`;
  wireRunButtons();
}

function wireRunButtons() {
  document.querySelectorAll('[data-detail]').forEach(button => button.onclick = () => details(Number(button.dataset.detail)));
  document.querySelectorAll('[data-cancel]').forEach(button => button.onclick = async () => {
    await api('/runs/' + button.dataset.cancel + '/cancel','POST'); show('running');
  });
  document.querySelectorAll('[data-cleanup]').forEach(button => button.onclick = async () => {
    await api('/runs/' + button.dataset.cleanup + '/cleanup','POST'); show('running');
  });
}

async function details(id) {
  selectedRun = id;
  if (eventStream) { eventStream.close(); eventStream = null; }
  const [run, logs, art, pkg, events] = await Promise.all([
    api('/runs/' + id), api('/runs/' + id + '/logs'), api('/runs/' + id + '/artifacts'),
    api('/runs/' + id + '/package'), api('/runs/' + id + '/events')
  ]);
  const target = document.getElementById('detail');
  if (!target || selectedRun !== id) return;
  selectedDeliveryPending = run.status === 'REVIEW' && ['pending','publishing'].includes(run.delivery_status);
  const ready = !art.pipeline_version || (art.ready_to_merge && ['ready','merged'].includes(run.delivery_status));
  const safePr = /^https:\/\/github\.com\//.test(run.pr_url || '') ? run.pr_url : '';
  target.innerHTML = `<h2>${t('run')} #${id}</h2><p id="run-status">${esc(stageName(run.stage || run.status))} ${esc(errorName(run.error))}</p>
    ${run.status === 'NEEDS_INPUT' ? `<form id="answer-form"><h3>${t('question')}</h3><p>${esc(run.question)}</p><textarea name="answer" required rows="5"></textarea><p><button>${t('answer')}</button></p></form>` : ''}
    <p>${t('sourceRepo')}: <code>${esc(run.source_path)}</code><br>${t('workspacePath')}: <code>${esc(run.workspace)}</code><br>${t('branch')}: <code>${esc(run.branch)}</code></p>
    <h3>${t('delivery')}</h3><p>${esc(run.delivery_status)} <span class="bad">${esc(run.delivery_error)}</span></p>
    ${safePr ? `<p><a href="${esc(safePr)}" target="_blank" rel="noopener">${esc(safePr)}</a></p>` : ''}
    ${run.delivery_repo ? `<p>${t('returned')}: <code>${esc(run.delivery_repo)}</code></p>` : ''}
    ${run.delivery_status === 'failed' && run.status === 'REVIEW' ? `<button id="retry-delivery">${t('retryDelivery')}</button>` : ''}
    <h3>${t('stages')}</h3><p>${(art.stages || []).map(x=>`${esc(stageName(x.name))}: ${esc(stateName(x.status))}`).join(' → ')}</p>
    ${art.plan ? `<h3>${t('plan')}</h3><p>${esc(art.plan.summary)}</p><ol>${art.plan.steps.map(x=>`<li><strong>${esc(x.title)}</strong><p>${esc(x.instructions)}</p></li>`).join('')}</ol>` : ''}
    ${art.code_review ? `<h3>${t('codeReview')} · ${art.code_review.passed ? t('passed') : t('blocked')}</h3><p>${esc(art.code_review.summary)}</p><ul>${art.code_review.findings.map(x=>`<li>${esc(x)}</li>`).join('')}</ul>` : ''}
    ${art.acceptance ? `<h3>${t('acceptance')} · ${art.acceptance.passed ? t('passed') : t('blocked')}</h3><p>${esc(art.acceptance.summary)}</p><ul>${art.acceptance.criteria.map(x=>`<li class="${x.passed ? 'good' : 'bad'}">${esc(x.criterion)}: ${esc(x.evidence)}</li>`).join('')}</ul>` : ''}
    <h3>${t('summary')}</h3><pre>${esc(art.agent_summary)}</pre>
    <h3>${t('files')}</h3><p>${esc((art.changed_files || []).join(', '))}</p>
    <h3>${t('gatesResult')}</h3>${(art.gates || []).map(gate => `<p class="${gate.exit_code ? 'bad' : 'good'}">${esc(gate.command)} — ${t('exitCode')} ${gate.exit_code}</p><pre>${esc(gate.output)}</pre>`).join('')}
    <details><summary>${t('package')}</summary><pre>${esc(JSON.stringify(pkg,null,2))}</pre></details>
    <h3>${t('diff')}</h3><pre>${esc(art.diff)}</pre>
    <h3>${t('eventTimeline')}</h3><div id="event-timeline">${events.filter(x => x.kind === 'status' || x.kind === 'agent').slice(-80).map(eventLine).join('')}</div>
    <h3>${t('logs')}</h3><pre id="log-view">${esc(logs.text)}</pre>
    ${run.status === 'REVIEW' ? `<button id="approve" ${ready ? '' : 'disabled'}>${pkg.delivery === 'github' ? t('approveMerge') : pkg.delivery === 'local' ? t('approveLocal') : t('approve')}</button><button id="reject">${t('reject')}</button>` : ''}`;
  const retry = document.getElementById('retry-delivery');
  const answerForm = document.getElementById('answer-form');
  if (answerForm) answerForm.onsubmit = async event => {
    event.preventDefault();
    const button = answerForm.querySelector('button'); button.disabled = true;
    try {
      await api('/runs/' + id + '/answer', 'POST', {answer:answerForm.elements.answer.value});
      await details(id);
    }
    finally { button.disabled = false; }
  };
  if (retry) retry.onclick = async () => { await api('/runs/' + id + '/publish','POST',{}); await details(id); };
  for (const decision of ['approve','reject']) {
    const button = document.getElementById(decision);
    if (button) button.onclick = async () => {
      button.disabled = true;
      try {
        await api('/runs/' + id + '/review','POST',{decision});
        const detailModal = document.getElementById('detail-modal');
        if (detailModal?.open) detailModal.close();
        await show(current);
      }
      finally { button.disabled = false; }
    };
  }
  openRunStream(id, events.length ? events[events.length - 1].id : 0);
}

function eventLine(item) {
  const data = item.data || {};
  const label = item.kind === 'status'
    ? `${stageName(data.stage || data.status)} · ${stateName(data.status)}`
    : `${data.title || data.type || 'Agent'} · ${data.status || ''}`;
  return `<p><small>${esc(item.created_at)}</small> ${esc(label)}</p>`;
}

function openRunStream(id, after) {
  eventStream = new EventSource(`/api/runs/${id}/stream?after=${after}`);
  eventStream.onmessage = message => {
    if (selectedRun !== id) return;
    const item = JSON.parse(message.data);
    const timeline = document.getElementById('event-timeline');
    const logView = document.getElementById('log-view');
    if (item.kind === 'log' && logView) logView.textContent += item.data.text;
    if (item.kind === 'agent' && logView) logView.textContent += item.data.raw || '';
    if ((item.kind === 'status' || item.kind === 'agent') && timeline) {
      timeline.insertAdjacentHTML('beforeend', eventLine(item));
      while (timeline.children.length > 80) timeline.firstElementChild.remove();
    }
    if (item.kind === 'status') {
      const status = document.getElementById('run-status');
      if (status) status.textContent = `${stageName(item.data.stage || item.data.status)} ${errorName(item.data.error)}`;
      if (['NEEDS_INPUT','REVIEW','FAILED','SUCCEEDED','REJECTED','CANCELLED'].includes(item.data.status)) {
        if (!document.getElementById('detail-modal')?.open) show(current);
      }
    }
  };
}

window.onunhandledrejection = event => alert(errorName(event.reason?.message || event.reason));
document.querySelectorAll('nav button[data-view]').forEach(button => button.onclick = () => {
  if (eventStream) { eventStream.close(); eventStream = null; }
  selectedRun = null;
  show(button.dataset.view);
});
show('board');
setInterval(() => {
  if (document.activeElement?.closest?.('#answer-form') || document.activeElement?.closest?.('#task-modal-form') || document.activeElement?.closest?.('#task-form')) return;
  if (eventStream && selectedRun && !selectedDeliveryPending) return;
  if (current === 'board' || current === 'running' || current === 'review') show(current);
}, 5000);
