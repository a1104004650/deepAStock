<template>
  <MainLayout>
    <div class="page">
      <!-- Layer 1: Competition List -->
      <div v-if="!selected" class="selection-layer">
        <div class="selection-header">
          <div>
            <h2 class="page-title">AI炒股比赛</h2>
            <p class="page-subtitle">多个AI智能体实时模拟交易对决</p>
          </div>
          <el-button type="primary" @click="openCreateDialog" round>
            <el-icon><Plus /></el-icon>新建比赛
          </el-button>
        </div>
        <div class="comp-grid">
          <div
            v-for="c in competitions"
            :key="c.id"
            class="comp-card"
            @click="enterCompetition(c)"
          >
            <div class="comp-card-header">
              <div class="comp-card-icon">🏆</div>
              <el-tag
                :type="statusTagType(c.status)"
                size="small"
                effect="dark"
                round
              >{{ statusLabel(c.status) }}</el-tag>
            </div>
            <div class="comp-card-body">
              <div class="comp-card-name">{{ c.name }}</div>
              <div class="comp-card-desc" v-if="c.description">{{ c.description }}</div>
              <div class="comp-card-meta">
                <span class="meta-item">
                  <el-icon><User /></el-icon>
                  {{ c.participant_count || 0 }} 选手
                </span>
                <span class="meta-item">¥{{ formatMoney(c.initial_capital) }}</span>
                <span class="meta-item">{{ formatDate(c.created_at) }}</span>
              </div>
            </div>
            <div class="comp-card-footer">
              <span>进入比赛</span>
              <el-icon><ArrowRight /></el-icon>
            </div>
          </div>
          <div v-if="!competitions.length && !loadingList" class="empty-state">
            <div class="empty-icon">🎯</div>
            <div class="empty-text">暂无比赛</div>
            <div class="empty-hint">点击上方按钮创建你的第一场AI对决</div>
          </div>
        </div>
      </div>

      <!-- Layer 2 & 3: Competition Dashboard + Arena -->
      <div v-else class="arena-layer">
        <!-- Hero Header -->
        <div class="arena-hero">
          <div class="arena-hero-left">
            <el-button text @click="leaveArena" class="back-btn">
              <el-icon size="20"><ArrowLeft /></el-icon>
            </el-button>
            <div class="arena-hero-info">
              <h2 class="arena-hero-title">{{ selected.name }}</h2>
              <el-tag
                :type="statusTagType(selected.status)"
                size="small"
                effect="dark"
                round
              >{{ statusLabel(selected.status) }}</el-tag>
            </div>
          </div>
          <div class="arena-hero-right">
            <el-button v-if="selected.status === 'setup'" type="success" :loading="actionLoading" @click="startCompetition" round>
              <el-icon><VideoPlay /></el-icon>开始比赛
            </el-button>
            <template v-if="selected.status === 'active'">
              <el-button type="warning" :loading="actionLoading" @click="pauseCompetition" round>
                <el-icon><VideoPause /></el-icon>暂停
              </el-button>
              <el-button type="danger" :loading="actionLoading" @click="finishCompetition" round>
                <el-icon><CircleCloseFilled /></el-icon>结束
              </el-button>
              <el-divider direction="vertical" />
              <el-button v-if="!aiRunning" type="success" :loading="aiStarting" @click="startAI" round>
                <el-icon><VideoPlay /></el-icon>启动AI自主运行
              </el-button>
              <el-button v-else type="danger" :loading="aiStopping" @click="stopAI" round>
                <el-icon><VideoPause /></el-icon>停止AI
              </el-button>
            </template>
            <template v-if="selected.status === 'paused'">
              <el-button type="success" :loading="actionLoading" @click="resumeCompetition" round>
                <el-icon><VideoPlay /></el-icon>恢复
              </el-button>
              <el-button type="danger" :loading="actionLoading" @click="finishCompetition" round>
                <el-icon><CircleCloseFilled /></el-icon>结束
              </el-button>
            </template>
            <el-button v-if="selected.status !== 'finished'" @click="openEditDialog" round>
              <el-icon><Edit /></el-icon>编辑设置
            </el-button>
            <el-button v-if="selected.status === 'setup' || selected.status === 'finished'" type="danger" :loading="actionLoading" @click="deleteCompetition" round>
              <el-icon><Delete /></el-icon>删除
            </el-button>
            <el-button v-if="selected.status !== 'setup'" type="warning" :loading="actionLoading" @click="resetCompetition" round>
              🔄 重置
            </el-button>
          </div>
        </div>

        <!-- Stats Cards -->
        <div v-if="statsLoaded" class="stats-row">
          <div class="stat-card">
            <div class="stat-value">{{ statsData.participants?.total ?? players.length }}</div>
            <div class="stat-label">参赛人数</div>
          </div>
          <div class="stat-card">
            <div class="stat-value">{{ statsData.trades?.total || 0 }}</div>
            <div class="stat-label">总交易次数</div>
          </div>
          <div class="stat-card">
            <div class="stat-value" :class="avgReturnClass">{{ avgReturn >= 0 ? '+' : '' }}{{ avgReturn }}%</div>
            <div class="stat-label">平均收益率</div>
          </div>
          <div class="stat-card">
            <div class="stat-value best">{{ bestPlayerName }}</div>
            <div class="stat-label">最佳选手</div>
          </div>
        </div>

        <!-- AI Auto-Run Status -->
        <div v-if="aiRunning && aiStatus" class="ai-status-bar">
          <div class="ai-status-left">
            <span class="ai-pulse"></span>
            <span class="ai-status-label">AI自主运行中</span>
            <el-tag size="small" effect="plain" round>第 {{ aiStatus.round || 0 }} 轮</el-tag>
          </div>
          <div class="ai-status-right">
            <div v-for="(p, i) in (aiStatus.participants || [])" :key="i" class="ai-player-status">
              <span>{{ p.avatar }}</span>
              <span class="ai-player-name">{{ p.name }}</span>
              <span :class="['ai-player-phase', p.phase]">{{ phaseLabel(p.phase) }}</span>
              <span v-if="p.trades_this_round" class="ai-player-trades">{{ p.trades_this_round }}笔</span>
            </div>
          </div>
        </div>

        <!-- Player Dashboard -->
        <div class="players-dashboard">
          <div class="dashboard-label">选手列表</div>
          <div class="players-scroll">
            <div
              v-for="(p, idx) in players"
              :key="p.id"
              class="player-card"
              :class="{ 'is-top': idx === 0 && players.length > 1 && (p.total_return || 0) > 0 }"
              @mouseenter="showPosTooltip(p, $event)"
              @mouseleave="startHideTimer"
            >
              <div class="player-card-top">
                <div class="player-rank" v-if="players.length > 1">#{{ idx + 1 }}</div>
                <el-button class="player-edit-btn" size="small" circle @click.stop="openEditPlayer(p)">
                  <el-icon><Edit /></el-icon>
                </el-button>
                <el-button class="player-remove-btn" size="small" circle @click.stop="removePlayer(p)" :loading="removingPlayerId === p.id">
                  <el-icon><Close /></el-icon>
                </el-button>
              </div>
              <div class="player-main">
                <div class="player-avatar-wrap">
                  <span class="player-avatar">{{ p.avatar }}</span>
                </div>
                <div class="player-info">
                  <div class="player-name">{{ p.name }}</div>
                  <div class="player-model">{{ p.provider }} / {{ p.model_name }}</div>
                </div>
              </div>
              <div :class="['player-return', (p.total_return || 0) >= 0 ? 'profit' : 'loss']">
                <span class="return-sign">{{ (p.total_return || 0) >= 0 ? '+' : '' }}</span>{{ ((p.total_return || 0) * 100).toFixed(2) }}%
              </div>
              <div class="player-trades">
                <span>总市值 ¥{{ formatMoney(p.total_assets ?? p.current_capital) }}</span>
                <span class="player-cash">余额 ¥{{ formatMoney(p.current_capital) }}</span>
              </div>
              <el-button v-if="selected.status === 'active'" size="small" type="primary" class="player-trade-btn" @click.stop="triggerPlayerTrade(p)" :loading="tradingPlayerId === p.id" round>
                交易一轮
              </el-button>
            </div>
            <div class="player-card add-player-card" @click="showAddPlayer = true">
              <el-icon size="28" color="#c0c4cc"><Plus /></el-icon>
              <span class="add-player-text">添加选手</span>
            </div>
          </div>
        </div>

        <!-- Leaderboard -->
        <div v-if="leaderboard.length > 0" class="leaderboard-panel">
          <div class="panel-header">
            <span class="panel-title">排行榜</span>
            <span class="panel-badge">{{ leaderboard.length }} 选手</span>
          </div>
          <el-table :data="leaderboard" size="small" stripe class="leaderboard-table" :show-header="true">
            <el-table-column label="排名" width="60" align="center">
              <template #default="{ row }">
                <span :class="['rank-badge', row.rank <= 3 ? 'top' : '']">{{ row.rank }}</span>
              </template>
            </el-table-column>
            <el-table-column label="选手" width="180">
              <template #default="{ row }">
                <div class="lb-player">
                  <span class="lb-avatar">{{ row.avatar }}</span>
                  <div>
                    <div class="lb-name">{{ row.name }}</div>
                    <div class="lb-model">{{ row.provider }} / {{ row.model_name }}</div>
                  </div>
                </div>
              </template>
            </el-table-column>
            <el-table-column label="收益率" width="100" align="right">
              <template #default="{ row }">
                <span :class="(row.total_return || 0) >= 0 ? 'profit' : 'loss'">
                  {{ (row.total_return || 0) >= 0 ? '+' : '' }}{{ ((row.total_return || 0) * 100).toFixed(2) }}%
                </span>
              </template>
            </el-table-column>
            <el-table-column label="胜率" width="80" align="right">
              <template #default="{ row }">
                {{ row.win_rate ? (row.win_rate * 100).toFixed(0) + '%' : '-' }}
              </template>
            </el-table-column>
            <el-table-column label="最大回撤" width="90" align="right">
              <template #default="{ row }">
                <span class="loss">{{ row.max_drawdown ? '-' + (row.max_drawdown * 100).toFixed(1) + '%' : '-' }}</span>
              </template>
            </el-table-column>
            <el-table-column label="总市值" width="110" align="right">
              <template #default="{ row }">
                <span>¥{{ formatMoney(row.total_assets ?? row.current_capital) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="交易次数" width="80" align="right" prop="total_trades" />
          </el-table>
        </div>

        <!-- Position Tooltip - Rich AI Panel -->
        <Teleport to="body">
          <div v-if="posTooltip.show" class="ai-panel" :style="{ left: posTooltip.x + 'px', top: posTooltip.y + 'px' }" @mouseenter="cancelHideTimer" @mouseleave="hidePosTooltip">
            <div class="ai-panel-header">
              <div class="ai-panel-player">
                <span class="ai-panel-avatar">{{ posTooltip.avatar }}</span>
                <div>
                  <div class="ai-panel-name">{{ posTooltip.player }}</div>
                  <div class="ai-panel-model">{{ posTooltip.provider }} / {{ posTooltip.model }}</div>
                </div>
              </div>
              <div :class="['ai-panel-return', posTooltip.totalReturn >= 0 ? 'profit' : 'loss']">
                {{ posTooltip.totalReturn >= 0 ? '+' : '' }}{{ (posTooltip.totalReturn * 100).toFixed(2) }}%
              </div>
            </div>

            <div class="ai-panel-tabs">
              <span :class="['ai-tab', posTooltip.tab === 'pos' && 'active']" @click="posTooltip.tab = 'pos'">持仓</span>
              <span :class="['ai-tab', posTooltip.tab === 'trades' && 'active']" @click="posTooltip.tab = 'trades'; loadPlayerTrades()">交割单</span>
              <span :class="['ai-tab', posTooltip.tab === 'curve' && 'active']" @click="posTooltip.tab = 'curve'; loadPlayerEquity()">收益</span>
            </div>

            <!-- 持仓 -->
            <div v-if="posTooltip.tab === 'pos'" class="ai-panel-body">
              <div v-if="posTooltip.positions && posTooltip.positions.length" class="ai-pos-list">
                <div v-for="(pos, i) in posTooltip.positions" :key="i" class="ai-pos-row">
                  <div class="ai-pos-left">
                    <span class="ai-pos-symbol">{{ pos.symbol }}</span>
                    <span class="ai-pos-name">{{ pos.name }}</span>
                  </div>
                  <div class="ai-pos-mid">
                    <span>{{ pos.quantity }}股</span>
                    <span class="ai-pos-cost">成本 {{ pos.avg_cost?.toFixed(2) }}</span>
                  </div>
                  <div :class="['ai-pos-pnl', (pos.unrealized_pnl || 0) >= 0 ? 'profit' : 'loss']">
                    {{ (pos.unrealized_pnl || 0) >= 0 ? '+' : '' }}{{ (pos.unrealized_pnl || 0).toFixed(0) }}
                  </div>
                </div>
              </div>
              <div v-else class="ai-panel-empty">空仓</div>
              <div class="ai-panel-footer">
                <span>总市值 ¥{{ formatMoney(posTooltip.totalAssets) }}</span>
                <span>余额 ¥{{ formatMoney(posTooltip.capital) }}</span>
                <span>交易 {{ posTooltip.trades }} 次</span>
              </div>
            </div>

            <!-- 交割单 -->
            <div v-if="posTooltip.tab === 'trades'" class="ai-panel-body">
              <div v-if="posTooltip.tradeList && posTooltip.tradeList.length" class="ai-trade-list">
                <div v-for="(t, i) in posTooltip.tradeList.slice(0, 15)" :key="i" class="ai-trade-row">
                  <el-tag :type="t.action === 'buy' ? 'danger' : 'success'" size="small" effect="dark" round class="ai-trade-tag">
                    {{ t.action === 'buy' ? '买' : '卖' }}
                  </el-tag>
                  <span class="ai-trade-sym">{{ t.symbol }}</span>
                  <span class="ai-trade-qty">{{ t.quantity }}股</span>
                  <span class="ai-trade-price">{{ t.price?.toFixed(2) }}</span>
                  <span class="ai-trade-time">{{ formatTimeShort(t.created_at) }}</span>
                </div>
              </div>
              <div v-else class="ai-panel-empty">暂无交易</div>
            </div>

            <!-- 收益曲线 -->
            <div v-if="posTooltip.tab === 'curve'" class="ai-panel-body">
              <div ref="playerChartRef" class="ai-curve-chart"></div>
            </div>
          </div>
        </Teleport>

        <!-- Main Content Grid -->
        <div class="arena-grid">
          <div class="grid-chart">
            <div class="panel-header">
              <span class="panel-title">收益曲线</span>
              <span class="panel-badge">{{ players.length }} 选手</span>
            </div>
            <div ref="chartRef" class="equity-chart"></div>
          </div>
          <div class="grid-chat">
            <div class="panel-header">
              <span class="panel-title">群聊</span>
              <span class="panel-badge">{{ messages.length }}</span>
            </div>
            <div class="chat-box">
              <div class="chat-messages" ref="chatBoxRef">
                <div
                  v-for="msg in messages"
                  :key="msg.id"
                  :class="['chat-msg', msg.participant_id ? (msg.message_type === 'debate' ? 'debate-msg' : msg.message_type === 'event' ? 'event-msg' : 'ai-msg') : 'user-msg']"
                >
                  <span class="chat-avatar">{{ msg.participant_avatar }}</span>
                  <div class="chat-body">
                    <div class="chat-name" v-if="msg.participant_name">{{ msg.participant_name }}</div>
                    <div class="chat-content">{{ msg.content }}</div>
                    <div class="chat-time">{{ formatTime(msg.created_at) }}</div>
                  </div>
                </div>
                <div v-if="!messages.length" class="chat-empty">
                  <span>💬</span>
                  <span>暂无消息</span>
                </div>
              </div>
              <div class="chat-input-wrap">
                <el-input v-model="chatInput" placeholder="发送消息..." size="small" @keyup.enter="sendChat" class="chat-input">
                  <template #append>
                    <el-button @click="sendChat" :disabled="!chatInput.trim()" type="primary">发送</el-button>
                  </template>
                </el-input>
              </div>
            </div>
          </div>
        </div>

        <!-- Trade Records -->
        <div class="trades-panel">
          <div class="panel-header">
            <span class="panel-title">交易记录</span>
            <span class="panel-badge">{{ allTrades.length }}</span>
          </div>
          <el-table :data="allTrades" size="small" stripe max-height="320" class="trades-table">
            <el-table-column label="选手" width="100">
              <template #default="{ row }">
                <div class="trade-player">
                  <span>{{ row.participant_avatar }}</span>
                  <span class="trade-player-name">{{ row.participant_name }}</span>
                </div>
              </template>
            </el-table-column>
            <el-table-column label="时间" width="140">
              <template #default="{ row }">
                <span class="trade-time">{{ formatTime(row.created_at) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="股票" width="140">
              <template #default="{ row }">
                <div class="trade-stock">
                  <span class="trade-symbol">{{ row.symbol }}</span>
                  <span class="trade-name" v-if="row.name">{{ row.name }}</span>
                </div>
              </template>
            </el-table-column>
            <el-table-column label="方向" width="60">
              <template #default="{ row }">
                <el-tag :type="row.action === 'buy' ? 'danger' : 'success'" size="small" effect="dark" round>
                  {{ row.action === 'buy' ? '买' : '卖' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="数量" width="70" align="right">
              <template #default="{ row }">{{ row.quantity }}</template>
            </el-table-column>
            <el-table-column label="价格" width="80" align="right">
              <template #default="{ row }">
                <span class="trade-price">{{ row.price?.toFixed(2) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="金额" width="90" align="right">
              <template #default="{ row }">
                <span class="trade-amount">{{ row.amount?.toFixed(0) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="手续费" width="65" align="right">
              <template #default="{ row }">
                <span class="trade-fee">{{ row.fee?.toFixed(1) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="理由" prop="reason" min-width="180" show-overflow-tooltip />
          </el-table>
        </div>

        <!-- Event Timeline -->
        <div v-if="events.length > 0" class="events-panel">
          <div class="panel-header">
            <span class="panel-title">事件时间线</span>
            <span class="panel-badge">{{ events.length }}</span>
          </div>
          <div class="events-list">
            <div v-for="ev in events.slice().reverse().slice(0, 20)" :key="ev.id" :class="['event-item', ev.type]">
              <div class="event-dot"></div>
              <div class="event-content">
                <div class="event-title">{{ ev.title }}</div>
                <div class="event-meta">
                  <span v-if="ev.participant" class="event-avatar">{{ ev.participant.avatar }}</span>
                  <span class="event-time">{{ formatTime(ev.created_at) }}</span>
                  <el-tag :type="eventTypeTag(ev.type)" size="small" effect="plain" round>{{ eventTypeLabel(ev.type) }}</el-tag>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Create Competition Dialog -->
    <el-dialog v-model="showCreateDialog" title="新建比赛" width="520px" destroy-on-close>
      <el-form label-position="top" size="small">
        <el-form-item label="比赛名称" required>
          <el-input v-model="compForm.name" placeholder="例如：第一届AI炒股大赛" />
        </el-form-item>
        <el-form-item label="比赛描述">
          <el-input v-model="compForm.description" type="textarea" :rows="2" placeholder="可选，描述比赛规则或主题" />
        </el-form-item>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="初始资金">
              <el-input-number v-model="compForm.initial_capital" :min="10000" :step="10000" style="width:100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="最大持仓比例(%)">
              <el-input-number v-model="compForm.max_position_pct" :min="1" :max="100" style="width:100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="最大持仓数">
              <el-input-number v-model="compForm.max_positions" :min="1" :max="50" style="width:100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="交易手续费(%)">
              <el-input-number v-model="compForm.trading_fee" :min="0" :max="1" :step="0.001" :precision="4" style="width:100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="股票池（可选）">
          <el-input v-model="poolInput" type="textarea" :rows="3" placeholder="每行一个股票代码，留空则不限制" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreateDialog = false">取消</el-button>
        <el-button type="primary" :loading="actionLoading" @click="createCompetition" :disabled="!compForm.name" round>创建</el-button>
      </template>
    </el-dialog>

    <!-- Edit Competition Dialog -->
    <el-dialog v-model="showEditDialog" title="编辑比赛设置" width="520px" destroy-on-close>
      <el-form label-position="top" size="small">
        <el-form-item label="比赛名称" required>
          <el-input v-model="editForm.name" placeholder="例如：第一届AI炒股大赛" />
        </el-form-item>
        <el-form-item label="比赛描述">
          <el-input v-model="editForm.description" type="textarea" :rows="2" placeholder="可选，描述比赛规则或主题" />
        </el-form-item>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="初始资金">
              <el-input-number v-model="editForm.initial_capital" :min="10000" :step="10000" style="width:100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="最大持仓比例(%)">
              <el-input-number v-model="editForm.max_position_pct" :min="1" :max="100" style="width:100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="最大持仓数">
              <el-input-number v-model="editForm.max_positions" :min="1" :max="50" style="width:100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="交易手续费(%)">
              <el-input-number v-model="editForm.trading_fee" :min="0" :max="1" :step="0.001" :precision="4" style="width:100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="股票池（可选）">
          <el-input v-model="editPoolInput" type="textarea" :rows="3" placeholder="每行一个股票代码，留空则不限制" />
        </el-form-item>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="自动交易">
              <el-switch v-model="editForm.auto_trade" active-text="开启" inactive-text="关闭" />
              <div class="form-hint">开启后系统在交易时段自动执行AI交易</div>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="交易间隔(分钟)">
              <el-input-number v-model="editForm.trade_interval_min" :min="5" :max="120" style="width:100%" />
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
      <template #footer>
        <el-button @click="showEditDialog = false">取消</el-button>
        <el-button type="primary" :loading="actionLoading" @click="updateCompetition" :disabled="!editForm.name" round>保存</el-button>
      </template>
    </el-dialog>

    <!-- Add/Edit Player Dialog -->
    <el-dialog v-model="showAddPlayer" :title="editingPlayerId ? '编辑AI选手' : '添加AI选手'" width="560px" destroy-on-close @close="resetPlayerForm">
      <div class="curl-section">
        <div class="curl-header">
          <span class="curl-icon">⚡</span>
          <span class="curl-title">CURL一键导入</span>
        </div>
        <el-input v-model="curlInput" type="textarea" :rows="3" placeholder="粘贴 curl 命令，自动解析 API 配置..." />
        <div class="curl-actions">
          <el-button size="small" type="primary" :loading="curlParsing" @click="parseCurl">解析</el-button>
          <div v-if="curlResult" :class="['curl-msg', curlOk ? 'ok' : 'err']">{{ curlResult }}</div>
        </div>
      </div>
      <el-divider content-position="center">
        <span style="font-size:12px;color:var(--el-text-color-placeholder)">或手动填写</span>
      </el-divider>
      <el-form label-position="top" size="small">
        <el-form-item label="选手名称" required>
          <el-input v-model="playerForm.name" placeholder="例如：DeepSeek战士" />
        </el-form-item>
        <el-form-item label="头像">
          <div class="avatar-picker">
            <div class="avatar-selected">{{ playerForm.avatar }}</div>
            <div class="avatar-grid">
              <span v-for="e in emojiList" :key="e" class="avatar-emoji" :class="{active: playerForm.avatar===e}" @click="playerForm.avatar=e">{{ e }}</span>
            </div>
          </div>
        </el-form-item>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="AI提供商" required>
              <el-select v-model="playerForm.provider" style="width:100%">
                <el-option label="DeepSeek" value="deepseek" />
                <el-option label="OpenAI" value="openai" />
                <el-option label="通义千问" value="qwen" />
                <el-option label="智谱GLM" value="zhipu" />
                <el-option label="Claude" value="claude" />
                <el-option label="Gemini" value="gemini" />
                <el-option label="Ollama(本地)" value="ollama" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="模型名称">
              <el-input v-model="playerForm.model_name" placeholder="例如：deepseek-chat">
                <template #append>
                  <el-button :loading="modelsLoading" @click="fetchModels" title="获取模型列表">
                    <el-icon><Refresh /></el-icon>
                  </el-button>
                </template>
              </el-input>
              <div v-if="modelList.length" class="model-list">
                <el-tag v-for="m in modelList" :key="m" size="small" :type="m === playerForm.model_name ? 'primary' : 'info'" class="model-tag" @click="playerForm.model_name = m">{{ m }}</el-tag>
              </div>
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="API Base">
          <el-input v-model="playerForm.api_base" placeholder="留空使用默认" />
        </el-form-item>
        <el-form-item label="API Key">
          <el-input v-model="playerForm.api_key" :placeholder="editingPlayerId ? '留空则保持不变' : 'API密钥'" show-password />
        </el-form-item>
        <el-form-item label="自定义系统提示词（可选）">
          <el-input v-model="playerForm.system_prompt" type="textarea" :rows="3" placeholder="留空使用默认交易策略" />
        </el-form-item>
      </el-form>
      <template #footer>
        <div style="display:flex;justify-content:space-between;align-items:center">
          <el-button v-if="editingPlayerId" type="info" text :loading="healthChecking" @click="checkHealth">
            检测AI状态
          </el-button>
          <div v-else></div>
          <div style="display:flex;gap:8px">
            <el-button @click="showAddPlayer = false">取消</el-button>
            <el-button type="primary" :loading="actionLoading" @click="savePlayer" :disabled="!playerForm.name || !playerForm.provider" round>{{ editingPlayerId ? '保存' : '添加' }}</el-button>
          </div>
        </div>
      </template>
    </el-dialog>
  </MainLayout>
</template>

<script setup>
import { ref, computed, onMounted, nextTick, onBeforeUnmount } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Plus, ArrowLeft, ArrowRight, VideoPlay, VideoPause,
  User, Edit, Delete, CircleCloseFilled, Refresh, Close
} from '@element-plus/icons-vue'
import MainLayout from '../../layout/MainLayout.vue'
import { labApi } from '../../api'
import * as echarts from 'echarts'

const competitions = ref([])
const loadingList = ref(false)
const selected = ref(null)
const players = ref([])
const actionLoading = ref(false)
const healthChecking = ref(false)
const aiStarting = ref(false)
const aiStopping = ref(false)
const aiRunning = ref(false)
const aiStatus = ref(null)
const tradingPlayerId = ref(null)
const removingPlayerId = ref(null)

const messages = ref([])
const allTrades = ref([])
const chatInput = ref('')
const chatBoxRef = ref(null)

const statsData = ref({})
const statsLoaded = ref(false)
const leaderboard = ref([])
const events = ref([])

const showCreateDialog = ref(false)
const compForm = ref({ name: '', description: '', initial_capital: 100000, max_position_pct: 30, max_positions: 10, trading_fee: 0.0003 })
const poolInput = ref('')

const showEditDialog = ref(false)
const editForm = ref({ name: '', description: '', initial_capital: 100000, max_position_pct: 30, max_positions: 10, trading_fee: 0.0003 })
const editPoolInput = ref('')

const showAddPlayer = ref(false)
const editingPlayerId = ref(null)
const playerForm = ref({
  name: '', avatar: '🤖', provider: 'deepseek',
  api_base: '', api_key: '', model_name: '', system_prompt: '',
})

const emojiList = ['🤖','🧠','🦊','🐯','🦁','🐻','🐲','🦅','🐺','🐗','🐴','🦄','🐔','🐧','🐦','🐤','🦆','🦅','🦉','🦇','🐝','🐛','🦋','🐌','🐞','🐜','🐢','🐍','🦎','🦖','🦕','🐙','🦑','🦐','🦞','🦀','🐡','🐠','🐟','🐬','🐳','🐋','🦈','🐊','🐅','🐆','🦓','🦍','🐘','🐪','🐫','🦒','🦘','🐃','🐂','🐄','🐎','🐖','🐏','🐑','🦙','🐐','🦌','🐕','🐩','🐈','🐓','🦚','🦜','🦢','🦩','🐇']

const curlInput = ref('')
const curlParsing = ref(false)
const curlResult = ref('')
const curlOk = ref(false)
const modelsLoading = ref(false)
const modelList = ref([])

const chartRef = ref(null)
let equityChart = null

const posTooltip = ref({ show: false, x: 0, y: 0, player: '', avatar: '', provider: '', model: '', positions: [], capital: 0, trades: 0, totalReturn: 0, tab: 'pos', tradeList: [], equity: [] })
const playerChartRef = ref(null)
let playerChart = null

const avgReturn = computed(() => {
  if (!players.value.length) return '0.00'
  const sum = players.value.reduce((acc, p) => acc + (p.total_return || 0), 0)
  return ((sum / players.value.length) * 100).toFixed(2)
})

const avgReturnClass = computed(() => {
  return parseFloat(avgReturn.value) >= 0 ? 'profit' : 'loss'
})

const bestPlayerName = computed(() => {
  if (!players.value.length) return '-'
  const sorted = [...players.value].sort((a, b) => (b.total_return || 0) - (a.total_return || 0))
  return sorted[0]?.name || '-'
})

function statusLabel(s) {
  const map = { setup: '筹备中', active: '进行中', paused: '已暂停', finished: '已结束' }
  return map[s] || s
}

function statusTagType(s) {
  const map = { setup: 'warning', active: 'success', paused: 'info', finished: 'info' }
  return map[s] || 'info'
}

function eventTypeLabel(t) {
  const map = { limit_up: '涨停', limit_down: '跌停', stop_loss: '止损', major_drawdown: '回撤', rank_change: '排名变化', trade: '交易' }
  return map[t] || t
}

function eventTypeTag(t) {
  const map = { limit_up: 'danger', limit_down: 'success', stop_loss: 'warning', major_drawdown: 'danger', rank_change: 'primary', trade: 'info' }
  return map[t] || 'info'
}

function formatTime(t) {
  if (!t) return ''
  // 后端已存上海时间，直接解析显示
  const d = new Date(t.replace(' ', 'T'))
  if (isNaN(d.getTime())) return t
  const m = d.getMonth() + 1
  const day = d.getDate()
  const h = d.getHours()
  const min = String(d.getMinutes()).padStart(2, '0')
  const sec = String(d.getSeconds()).padStart(2, '0')
  return `${m}/${day} ${h}:${min}:${sec}`
}

function formatDate(t) {
  if (!t) return ''
  const d = new Date(t)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

function formatMoney(v) {
  if (v == null) return '0'
  if (v >= 10000) return (v / 10000).toFixed(0) + '万'
  return v.toLocaleString()
}

async function loadCompetitions() {
  loadingList.value = true
  try {
    const res = await labApi.competitions()
    competitions.value = Array.isArray(res) ? res : (res.data || [])
  } catch { competitions.value = [] }
  loadingList.value = false
}

async function enterCompetition(c) {
  try {
    const res = await labApi.getCompetition(c.id)
    selected.value = res.data || res
    players.value = selected.value.participants || []
    // 并行加载所有数据
    await Promise.all([
      loadStats(),
      loadLeaderboard(),
      loadEvents(),
      loadChat(),
      loadAllTrades(),
      loadEquityCurve(),
      checkAIStatus()
    ])
    if (aiRunning.value) startAIPolling()
  } catch (e) {
    selected.value = c
    players.value = c.participants || []
  }
}

function leaveArena() {
  selected.value = null
  players.value = []
  messages.value = []
  allTrades.value = []
  statsLoaded.value = false
  statsData.value = {}
  leaderboard.value = []
  events.value = []
  aiRunning.value = false
  aiStatus.value = null
  stopAIPolling()
  hidePosTooltip()
  if (equityChart) {
    equityChart.dispose()
    equityChart = null
  }
}

async function loadStats() {
  if (!selected.value) return
  try {
    const res = await labApi.competitionStats(selected.value.id)
    statsData.value = res.data || res
    statsLoaded.value = true
  } catch {
    statsLoaded.value = true
  }
}

async function loadLeaderboard() {
  if (!selected.value) return
  try {
    const res = await labApi.leaderboard(selected.value.id)
    leaderboard.value = Array.isArray(res) ? res : (res.data || [])
  } catch { leaderboard.value = [] }
}

async function loadEvents() {
  if (!selected.value) return
  try {
    const res = await labApi.events(selected.value.id)
    events.value = Array.isArray(res) ? res : (res.data || [])
  } catch { events.value = [] }
}

async function loadChat() {
  if (!selected.value) return
  try {
    const res = await labApi.chat(selected.value.id)
    const all = Array.isArray(res) ? res : (res.data || [])
    messages.value = all.filter(m => m.message_type !== 'system')
    await nextTick()
    // 只在用户已经在底部时自动滚动，避免打断阅读
    if (chatBoxRef.value) {
      const el = chatBoxRef.value
      const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 150
      if (nearBottom) el.scrollTop = el.scrollHeight
    }
  } catch { messages.value = [] }
}

async function loadAllTrades() {
  if (!players.value.length) { allTrades.value = []; return }
  const results = await Promise.allSettled(
    players.value.map(p => labApi.participantTrades(p.id).then(res => {
      const list = Array.isArray(res) ? res : (res.data || [])
      list.forEach(t => { t.participant_avatar = p.avatar; t.participant_name = p.name })
      return list
    }))
  )
  const all = results.filter(r => r.status === 'fulfilled').flatMap(r => r.value)
  all.sort((a, b) => new Date(b.created_at) - new Date(a.created_at))
  allTrades.value = all
}

async function loadEquityCurve() {
  if (!selected.value) return
  try {
    const res = await labApi.equityCurve(selected.value.id)
    const data = res.data || res
    await nextTick()
    renderChart(data)
  } catch {}
}

function renderChart(data) {
  if (!chartRef.value) return

  const colors = ['#409eff', '#ef232a', '#14b143', '#e6a23c', '#909399', '#f56c6c', '#67c23a', '#b37feb']
  const players = Array.isArray(data) ? data : (data?.players || [])

  // 收集所有时间点作为x轴（取并集，按时间排序）
  const allTimes = new Set()
  players.forEach(p => (p.equity || []).forEach(e => allTimes.add(e.time)))
  const rawTimes = [...allTimes].sort()
  const xData = rawTimes.map(t => {
    // 格式化为 MM/DD HH:MM
    const d = new Date(t.replace(' ', 'T'))
    if (isNaN(d.getTime())) return t
    return `${d.getMonth()+1}/${d.getDate()} ${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}`
  })

  const series = []
  if (players.length) {
    players.forEach((p, i) => {
      // 构建 time->value 映射，用原始时间对齐
      const timeMap = {}
      ;(p.equity || []).forEach(e => { timeMap[e.time] = e.value })
      series.push({
        name: p.name,
        type: 'line',
        data: rawTimes.map(t => timeMap[t] ?? null),
        smooth: true,
        showSymbol: false,
        lineStyle: { width: 2.5 },
        itemStyle: { color: colors[i % colors.length] },
        areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: colors[i % colors.length] + '20' },
          { offset: 1, color: colors[i % colors.length] + '02' },
        ])},
      })
    })
  }

  if (!equityChart) {
    equityChart = echarts.init(chartRef.value)
  }
  equityChart.setOption({
    tooltip: {
      trigger: 'axis',
      backgroundColor: 'rgba(255,255,255,0.95)',
      borderColor: '#ebeef5',
      textStyle: { fontSize: 12 },
    },
    legend: { top: 0, textStyle: { fontSize: 11 } },
    grid: { left: 55, right: 16, top: 35, bottom: 24 },
    xAxis: { type: 'category', data: xData, boundaryGap: false, axisLabel: { fontSize: 10, rotate: 30 }, axisLine: { lineStyle: { color: '#dcdfe6' } } },
    yAxis: { type: 'value', axisLabel: { fontSize: 10, formatter: v => (v / 10000).toFixed(1) + '万' }, splitLine: { lineStyle: { type: 'dashed', color: '#ebeef5' } } },
    series,
  }, true)
}

function openCreateDialog() {
  compForm.value = { name: '', description: '', initial_capital: 100000, max_position_pct: 30, max_positions: 10, trading_fee: 0.0003 }
  poolInput.value = ''
  showCreateDialog.value = true
}

function openEditDialog() {
  if (!selected.value) return
  editForm.value = {
    name: selected.value.name ?? '',
    description: selected.value.description ?? '',
    initial_capital: selected.value.initial_capital ?? 100000,
    max_position_pct: selected.value.max_position_pct ?? 30,
    max_positions: selected.value.max_positions ?? 10,
    trading_fee: selected.value.trading_fee ?? 0.0003,
    auto_trade: selected.value.auto_trade !== false,
    trade_interval_min: selected.value.trade_interval_min ?? 30,
  }
  const pool = selected.value.stock_pool
  editPoolInput.value = Array.isArray(pool) ? pool.join('\n') : (pool || '')
  showEditDialog.value = true
}

async function createCompetition() {
  actionLoading.value = true
  try {
    const pool = poolInput.value.trim()
      ? poolInput.value.split('\n').map(s => s.trim()).filter(Boolean)
      : null
    await labApi.createCompetition({ ...compForm.value, stock_pool: pool })
    ElMessage.success('创建成功')
    showCreateDialog.value = false
    await loadCompetitions()
  } finally { actionLoading.value = false }
}

async function updateCompetition() {
  actionLoading.value = true
  try {
    const pool = editPoolInput.value.trim()
      ? editPoolInput.value.split('\n').map(s => s.trim()).filter(Boolean)
      : null
    await labApi.updateCompetition(selected.value.id, { ...editForm.value, stock_pool: pool })
    ElMessage.success('保存成功')
    showEditDialog.value = false
    await enterCompetition(selected.value)
  } finally { actionLoading.value = false }
}

async function deleteCompetition() {
  try {
    await ElMessageBox.confirm('确定删除该比赛？此操作不可恢复。', '删除确认', { type: 'warning', confirmButtonText: '确定删除', cancelButtonText: '取消' })
  } catch { return }
  actionLoading.value = true
  try {
    await labApi.deleteCompetition(selected.value.id)
    ElMessage.success('已删除')
    await leaveArena()
    await loadCompetitions()
  } finally { actionLoading.value = false }
}

async function startCompetition() {
  actionLoading.value = true
  try {
    await labApi.startCompetition(selected.value.id)
    ElMessage.success('比赛已开始')
    await enterCompetition(selected.value)
  } finally { actionLoading.value = false }
}

async function pauseCompetition() {
  actionLoading.value = true
  try {
    await labApi.pauseCompetition(selected.value.id)
    ElMessage.success('比赛已暂停')
    await enterCompetition(selected.value)
  } finally { actionLoading.value = false }
}

async function resumeCompetition() {
  actionLoading.value = true
  try {
    await labApi.resumeCompetition(selected.value.id)
    ElMessage.success('比赛已恢复')
    await enterCompetition(selected.value)
  } finally { actionLoading.value = false }
}

async function finishCompetition() {
  try {
    await ElMessageBox.confirm('确定结束比赛？', '确认', { type: 'warning' })
  } catch { return }
  actionLoading.value = true
  try {
    await labApi.finishCompetition(selected.value.id)
    ElMessage.success('比赛已结束')
    await enterCompetition(selected.value)
  } finally { actionLoading.value = false }
}

async function resetCompetition() {
  try {
    await ElMessageBox.confirm('确定重置比赛？将清除所有交易记录、持仓和聊天记录，此操作不可恢复。', '重置确认', { type: 'warning', confirmButtonText: '确定重置', cancelButtonText: '取消' })
  } catch { return }
  actionLoading.value = true
  try {
    await labApi.resetCompetition(selected.value.id)
    ElMessage.success('比赛已重置')
    await enterCompetition(selected.value)
  } finally { actionLoading.value = false }
}

// ==================== AI自主运行 ====================

let aiPollTimer = null

function phaseLabel(phase) {
  const map = { idle: '待命', thinking: '思考中', analyzing: '分析中', discussing: '讨论中', trading: '交易中', done: '完成', error: '出错', waiting: '等待中' }
  return map[phase] || phase
}

async function checkAIStatus() {
  if (!selected.value) return
  try {
    const res = await labApi.aiStatus(selected.value.id)
    const data = res.data || res
    aiRunning.value = data.running
    aiStatus.value = data.status
  } catch {
    aiRunning.value = false
    aiStatus.value = null
  }
}

function startAIPolling() {
  stopAIPolling()
  let pollCount = 0
  aiPollTimer = setInterval(async () => {
    await checkAIStatus()
    if (aiRunning.value) {
      await loadChat()
      await loadAllTrades()
      // 每5轮(25秒)刷新一次曲线
      pollCount++
      if (pollCount % 5 === 0) {
        await loadEquityCurve()
        await loadLeaderboard()
        await loadEvents()
      }
    }
  }, 5000)
  checkAIStatus()
}

function stopAIPolling() {
  if (aiPollTimer) { clearInterval(aiPollTimer); aiPollTimer = null }
}

async function startAI() {
  aiStarting.value = true
  try {
    await labApi.aiStart(selected.value.id)
    ElMessage.success('AI自主运行已启动')
    await checkAIStatus()
    startAIPolling()
  } finally { aiStarting.value = false }
}

async function stopAI() {
  aiStopping.value = true
  try {
    await labApi.aiStop(selected.value.id)
    ElMessage.success('AI自主运行已停止')
    aiRunning.value = false
    aiStatus.value = null
    stopAIPolling()
    await enterCompetition(selected.value)
  } finally { aiStopping.value = false }
}

async function removePlayer(p) {
  try {
    await ElMessageBox.confirm(`确定移除选手「${p.name}」？`, '移除确认', { type: 'warning' })
  } catch { return }
  removingPlayerId.value = p.id
  try {
    await labApi.removeParticipant(p.id)
    ElMessage.success('已移除')
    await enterCompetition(selected.value)
  } finally { removingPlayerId.value = null }
}

async function triggerPlayerTrade(p) {
  tradingPlayerId.value = p.id
  try {
    await labApi.triggerParticipantTrade(selected.value.id, p.id)
    ElMessage.success(`${p.name} 交易指令已发送`)
    await enterCompetition(selected.value)
  } finally { tradingPlayerId.value = null }
}

function resetPlayerForm() {
  editingPlayerId.value = null
  playerForm.value = {
    name: '', avatar: '🤖', provider: 'deepseek',
    api_base: '', api_key: '', model_name: '', system_prompt: '',
  }
  curlInput.value = ''
  curlResult.value = ''
  modelList.value = []
}

async function openEditPlayer(p) {
  editingPlayerId.value = p.id
  playerForm.value = {
    name: p.name, avatar: p.avatar || '🤖', provider: p.provider || 'deepseek',
    api_base: p.api_base || '', api_key: '', model_name: p.model_name || '',
    system_prompt: p.system_prompt || '',
  }
  showAddPlayer.value = true
}

async function checkHealth() {
  if (!editingPlayerId.value) return
  healthChecking.value = true
  try {
    const res = await labApi.checkParticipantHealth(editingPlayerId.value)
    const data = res.data || res
    if (data.ok) {
      ElMessage.success(`AI连接正常 (${data.provider}/${data.model}, ${data.latency_ms}ms)`)
    } else {
      ElMessage.error(`AI连接失败: ${data.error}`)
    }
  } catch (e) {
    ElMessage.error('检测请求失败')
  } finally { healthChecking.value = false }
}

async function savePlayer() {
  actionLoading.value = true
  try {
    if (editingPlayerId.value) {
      await labApi.updateParticipant(editingPlayerId.value, playerForm.value)
      ElMessage.success('保存成功')
    } else {
      await labApi.addParticipant(selected.value.id, playerForm.value)
      ElMessage.success('添加成功')
    }
    showAddPlayer.value = false
    resetPlayerForm()
    await enterCompetition(selected.value)
  } finally { actionLoading.value = false }
}

async function fetchModels() {
  if (!playerForm.value.api_base) { ElMessage.warning('请先填写 API 地址'); return }
  modelsLoading.value = true
  modelList.value = []
  try {
    const r = await labApi.fetchModels({ api_base: playerForm.value.api_base, api_key: playerForm.value.api_key })
    if (r.models?.length) {
      modelList.value = r.models
      ElMessage.success(`获取到 ${r.models.length} 个模型`)
    } else {
      ElMessage.warning(r.error || '未获取到模型列表')
    }
  } catch (e) {
    ElMessage.error('获取模型列表失败')
  } finally {
    modelsLoading.value = false
  }
}

async function sendChat() {
  if (!chatInput.value.trim()) return
  try {
    await labApi.sendChat(selected.value.id, chatInput.value)
    chatInput.value = ''
    await loadChat()
  } catch {}
}

async function parseCurl() {
  if (!curlInput.value.trim()) return
  curlParsing.value = true
  curlResult.value = ''
  try {
    const data = await labApi.parseCurl(curlInput.value.trim())
    if (data.api_key) {
      if (data.api_base || data.base_url) playerForm.value.api_base = data.base_url || data.api_base
      if (data.api_key) playerForm.value.api_key = data.api_key
      if (data.model_name || data.model) playerForm.value.model_name = data.model_name || data.model
      if (data.provider) playerForm.value.provider = data.provider
      curlResult.value = '解析成功！已自动填充配置'
      curlOk.value = true
    } else {
      curlResult.value = '解析完成，未检测到有效配置'
      curlOk.value = false
    }
  } catch (e) {
    curlResult.value = '解析失败：' + (e.response?.data?.detail || e.message)
    curlOk.value = false
  }
  curlParsing.value = false
}

let hideTimer = null

async function showPosTooltip(player, event) {
  cancelHideTimer()
  const rect = event.currentTarget.getBoundingClientRect()
  let x = rect.left
  let y = rect.bottom + 8
  if (x + 380 > window.innerWidth) x = window.innerWidth - 390
  if (y + 400 > window.innerHeight) y = rect.top - 408

  const requestId = Date.now()
  posTooltip.value = {
    show: true, x, y,
    player: player.name,
    avatar: player.avatar || '🤖',
    provider: player.provider || '',
    model: player.model_name || '',
    totalReturn: player.total_return || 0,
    totalAssets: player.total_assets || 0,
    capital: player.current_capital || 0,
    trades: player.total_trades || 0,
    tab: 'pos',
    positions: [],
    tradeList: [],
    equity: [],
    _id: player.id,
    _requestId: requestId,
  }

  try {
    const res = await labApi.participantPositions(player.id)
    if (posTooltip.value._requestId === requestId) {
      posTooltip.value.positions = Array.isArray(res) ? res : (res.data || [])
    }
  } catch { if (posTooltip.value._requestId === requestId) posTooltip.value.positions = [] }
}

function startHideTimer() {
  hideTimer = setTimeout(() => { hidePosTooltip() }, 250)
}

function cancelHideTimer() {
  if (hideTimer) { clearTimeout(hideTimer); hideTimer = null }
}

async function loadPlayerTrades() {
  const pid = posTooltip.value._id
  if (!pid) return
  try {
    const res = await labApi.participantTrades(pid)
    posTooltip.value.tradeList = Array.isArray(res) ? res : (res.data || [])
  } catch { posTooltip.value.tradeList = [] }
}

async function loadPlayerEquity() {
  const pid = posTooltip.value._id
  if (!pid) return
  await loadPlayerTrades()
  if (!posTooltip.value.equity.length) {
    try {
      const res = await labApi.equityCurve(selected.value.id)
      const curves = Array.isArray(res) ? res : (res.data || res)
      const myCurve = curves.find(c => c.participant_id === pid)
      if (myCurve) {
        posTooltip.value.equity = myCurve.equity || []
        await nextTick()
        renderPlayerChart(myCurve)
      }
    } catch {}
  }
}

function renderPlayerChart(curveData) {
  if (!playerChartRef.value || !curveData) return
  if (playerChart) playerChart.dispose()
  playerChart = echarts.init(playerChartRef.value)

  const data = (curveData.equity || []).map(e => [e.time, e.value])

  playerChart.setOption({
    grid: { left: 45, right: 10, top: 10, bottom: 20 },
    xAxis: {
      type: 'category',
      data: data.map(d => d[0]),
      show: false,
    },
    yAxis: {
      type: 'value',
      axisLabel: { fontSize: 9, formatter: v => (v / 10000).toFixed(1) + '万' },
      splitLine: { lineStyle: { type: 'dashed', color: '#ebeef5' } },
    },
    series: [{
      type: 'line',
      data: data.map(d => d[1]),
      smooth: true,
      showSymbol: false,
      lineStyle: { width: 2, color: '#409eff' },
      areaStyle: {
        color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: 'rgba(64,158,255,0.15)' },
          { offset: 1, color: 'rgba(64,158,255,0.01)' },
        ]),
      },
    }],
    tooltip: {
      trigger: 'axis',
      formatter: params => {
        const v = params[0]?.value
        return v ? `¥${v.toFixed(0)}` : ''
      },
      backgroundColor: 'rgba(255,255,255,0.95)',
      borderColor: '#ebeef5',
    },
  })
}

function hidePosTooltip() {
  cancelHideTimer()
  posTooltip.value.show = false
  if (playerChart) { playerChart.dispose(); playerChart = null }
}

function formatTimeShort(t) {
  if (!t) return ''
  const d = new Date(t.replace(' ', 'T'))
  if (isNaN(d.getTime())) return t
  return `${d.getHours()}:${String(d.getMinutes()).padStart(2, '0')}`
}

function onResize() { equityChart?.resize() }

onMounted(() => {
  loadCompetitions()
  window.addEventListener('resize', onResize)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', onResize)
  stopAIPolling()
  cancelHideTimer()
  if (equityChart) { equityChart.dispose(); equityChart = null }
})
</script>

<style scoped>
.page {
  height: 100%;
  --panel-bg: var(--el-bg-color);
  --panel-border: var(--el-border-color-lighter);
  --panel-radius: 12px;
  --hero-bg: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
}

/* ===== Selection Layer ===== */
.selection-header {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  margin-bottom: 24px;
}
.page-title {
  font-size: 22px;
  font-weight: 800;
  margin: 0;
  letter-spacing: -0.3px;
}
.page-subtitle {
  font-size: 13px;
  color: var(--el-text-color-secondary);
  margin: 4px 0 0 0;
}

/* Competition Cards Grid */
.comp-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 16px;
}
.comp-card {
  background: var(--panel-bg);
  border: 1px solid var(--panel-border);
  border-radius: 12px;
  overflow: hidden;
  cursor: pointer;
  transition: all 0.3s ease;
}
.comp-card:hover {
  border-color: transparent;
  box-shadow: 0 8px 30px rgba(0,0,0,0.1);
  transform: translateY(-3px);
}
.comp-card:hover .comp-card-footer { color: var(--el-color-primary); }
.comp-card:hover .comp-card-footer el-icon { transform: translateX(3px); }

.comp-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 18px 12px;
}
.comp-card-icon { font-size: 24px; }
.comp-card-body { padding: 0 18px 14px; }
.comp-card-name {
  font-size: 17px;
  font-weight: 700;
  margin-bottom: 6px;
}
.comp-card-desc {
  font-size: 13px;
  color: var(--el-text-color-secondary);
  line-height: 1.5;
  margin-bottom: 12px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.comp-card-meta {
  display: flex;
  gap: 14px;
  flex-wrap: wrap;
}
.meta-item {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.comp-card-footer {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 10px 18px;
  border-top: 1px solid var(--panel-border);
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-secondary);
  transition: color 0.2s;
}
.comp-card-footer el-icon { transition: transform 0.2s; }

/* Empty state */
.empty-state {
  grid-column: 1 / -1;
  text-align: center;
  padding: 60px 20px;
  background: var(--panel-bg);
  border: 2px dashed var(--panel-border);
  border-radius: 12px;
}
.empty-icon { font-size: 40px; margin-bottom: 12px; }
.empty-text { font-size: 16px; font-weight: 600; margin-bottom: 4px; }
.empty-hint { font-size: 13px; color: var(--el-text-color-placeholder); }

/* ===== Arena Layer ===== */
.arena-layer {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* Arena Hero Header */
.arena-hero {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: var(--hero-bg);
  border-radius: var(--panel-radius);
  padding: 16px 24px;
  color: #fff;
}
.arena-hero-left {
  display: flex;
  align-items: center;
  gap: 12px;
}
.back-btn { color: rgba(255,255,255,0.8); font-size: 18px; }
.back-btn:hover { color: #fff; }
.arena-hero-info {
  display: flex;
  align-items: center;
  gap: 10px;
}
.arena-hero-title {
  font-size: 20px;
  font-weight: 700;
  margin: 0;
}
.arena-hero-right {
  display: flex;
  gap: 8px;
  align-items: center;
}
.auto-trade-tag {
  margin-left: 4px;
}
.form-hint {
  font-size: 11px;
  color: var(--el-text-color-placeholder);
  margin-top: 4px;
}

/* AI Auto-Run Status Bar */
.ai-status-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: linear-gradient(135deg, #f0f9eb 0%, #e1f3d8 100%);
  border: 1px solid #b3e19d;
  border-radius: var(--panel-radius);
  padding: 12px 20px;
  gap: 16px;
  flex-wrap: wrap;
}
.ai-status-left {
  display: flex;
  align-items: center;
  gap: 10px;
}
.ai-pulse {
  width: 10px;
  height: 10px;
  background: #67c23a;
  border-radius: 50%;
  animation: pulse 1.5s ease-in-out infinite;
}
@keyframes pulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.5; transform: scale(1.3); }
}
.ai-status-label {
  font-size: 14px;
  font-weight: 700;
  color: #67c23a;
}
.ai-status-right {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}
.ai-player-status {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  background: rgba(255,255,255,0.7);
  padding: 4px 10px;
  border-radius: 8px;
}
.ai-player-name {
  font-weight: 600;
}
.ai-player-phase {
  font-size: 11px;
  padding: 1px 6px;
  border-radius: 4px;
  background: var(--el-fill-color);
}
.ai-player-phase.analyzing { color: #409eff; background: #ecf5ff; }
.ai-player-phase.trading { color: #e6a23c; background: #fdf6ec; }
.ai-player-phase.done { color: #67c23a; background: #f0f9eb; }
.ai-player-phase.error { color: #f56c6c; background: #fef0f0; }
.ai-player-phase.thinking { color: #909399; background: #f4f4f5; }
.ai-player-trades {
  color: var(--el-color-primary);
  font-weight: 600;
}

/* Stats Row */
.stats-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
}
.stat-card {
  background: var(--panel-bg);
  border: 1px solid var(--panel-border);
  border-radius: var(--panel-radius);
  padding: 20px;
  text-align: center;
  transition: all 0.2s;
}
.stat-card:hover {
  box-shadow: 0 4px 16px rgba(0,0,0,0.06);
}
.stat-value {
  font-size: 28px;
  font-weight: 800;
  color: var(--el-text-color-primary);
  margin-bottom: 4px;
  letter-spacing: -0.5px;
}
.stat-value.profit { color: #ef232a; }
.stat-value.loss { color: #14b143; }
.stat-value.best {
  font-size: 18px;
  font-weight: 700;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 100%;
}
.stat-label {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

/* Players Dashboard */
.players-dashboard {
  background: var(--panel-bg);
  border: 1px solid var(--panel-border);
  border-radius: var(--panel-radius);
  padding: 16px;
}
.dashboard-label {
  font-size: 15px;
  font-weight: 700;
  margin-bottom: 12px;
}
.players-scroll {
  display: flex;
  gap: 12px;
  overflow-x: auto;
  padding: 4px 0;
  scrollbar-width: thin;
}
.player-card {
  position: relative;
  min-width: 180px;
  background: var(--panel-bg);
  border: 1px solid var(--panel-border);
  border-radius: 12px;
  padding: 14px 16px;
  flex-shrink: 0;
  cursor: default;
  transition: all 0.2s;
}
.player-card:hover {
  box-shadow: 0 4px 16px rgba(0,0,0,0.08);
  border-color: var(--el-color-primary-light-5);
}
.player-card.is-top {
  border-color: var(--el-color-warning-light-5);
  background: linear-gradient(135deg, var(--panel-bg) 0%, #fdf6ec 100%);
}
.player-card-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}
.player-rank {
  font-size: 11px;
  font-weight: 700;
  color: var(--el-text-color-placeholder);
}
.player-remove-btn {
  opacity: 0;
  transition: opacity 0.2s;
}
.player-edit-btn {
  opacity: 0;
  transition: opacity 0.2s;
}
.player-card:hover .player-remove-btn,
.player-card:hover .player-edit-btn {
  opacity: 1;
}
.player-main {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
}
.player-avatar-wrap {
  width: 40px;
  height: 40px;
  background: var(--el-fill-color-lighter);
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.player-avatar { font-size: 22px; }
.player-info { flex: 1; min-width: 0; }
.player-name {
  font-size: 14px;
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.player-model {
  font-size: 11px;
  color: var(--el-text-color-placeholder);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.player-return {
  font-size: 18px;
  font-weight: 800;
  letter-spacing: -0.5px;
  margin-bottom: 4px;
}
.return-sign { font-size: 14px; }
.player-trades {
  font-size: 11px;
  color: var(--el-text-color-placeholder);
  margin-bottom: 8px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.player-cash { opacity: 0.7; }
.player-trade-btn { width: 100%; }

.add-player-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  border-style: dashed;
  cursor: pointer;
  min-height: 180px;
}
.add-player-card:hover {
  border-color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
}
.add-player-text {
  font-size: 13px;
  color: var(--el-text-color-placeholder);
}

/* AI Player Panel (Hover) */
.ai-panel {
  position: fixed;
  background: #fff;
  border-radius: 12px;
  box-shadow: 0 12px 40px rgba(0,0,0,0.18);
  z-index: 2000;
  width: 370px;
  max-height: 420px;
  overflow: hidden;
  border: 1px solid var(--el-border-color-lighter);
}
.ai-panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 16px 10px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}
.ai-panel-player {
  display: flex;
  align-items: center;
  gap: 10px;
}
.ai-panel-avatar {
  font-size: 28px;
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--el-fill-color-lighter);
  border-radius: 10px;
}
.ai-panel-name { font-size: 15px; font-weight: 700; }
.ai-panel-model { font-size: 11px; color: var(--el-text-color-placeholder); }
.ai-panel-return {
  font-size: 20px;
  font-weight: 800;
  font-family: var(--font-mono, monospace);
}

/* Tabs */
.ai-panel-tabs {
  display: flex;
  border-bottom: 1px solid var(--el-border-color-lighter);
}
.ai-tab {
  flex: 1;
  text-align: center;
  padding: 8px 0;
  font-size: 12px;
  font-weight: 600;
  color: var(--el-text-color-secondary);
  cursor: pointer;
  border-bottom: 2px solid transparent;
  transition: all 0.2s;
}
.ai-tab:hover { color: var(--el-color-primary); }
.ai-tab.active {
  color: var(--el-color-primary);
  border-bottom-color: var(--el-color-primary);
}

/* Body */
.ai-panel-body {
  padding: 10px 14px;
  max-height: 280px;
  overflow-y: auto;
}

/* Position list */
.ai-pos-list { display: flex; flex-direction: column; gap: 6px; }
.ai-pos-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 8px;
  background: var(--el-fill-color-lighter);
  border-radius: 6px;
  font-size: 12px;
}
.ai-pos-left { display: flex; flex-direction: column; }
.ai-pos-symbol { font-weight: 700; font-family: var(--font-mono, monospace); }
.ai-pos-name { font-size: 10px; color: var(--el-text-color-placeholder); }
.ai-pos-mid { display: flex; flex-direction: column; align-items: flex-end; color: var(--el-text-color-secondary); }
.ai-pos-cost { font-size: 10px; color: var(--el-text-color-placeholder); }
.ai-pos-pnl { font-weight: 700; font-family: var(--font-mono, monospace); }

/* Trade list */
.ai-trade-list { display: flex; flex-direction: column; gap: 4px; }
.ai-trade-row {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  padding: 3px 0;
}
.ai-trade-tag { flex-shrink: 0; }
.ai-trade-sym { font-weight: 600; font-family: var(--font-mono, monospace); width: 56px; }
.ai-trade-qty { color: var(--el-text-color-secondary); width: 45px; }
.ai-trade-price { font-family: var(--font-mono, monospace); width: 55px; }
.ai-trade-time { color: var(--el-text-color-placeholder); margin-left: auto; font-family: var(--font-mono, monospace); }

/* Footer */
.ai-panel-footer {
  display: flex;
  justify-content: space-between;
  padding: 8px 14px;
  border-top: 1px solid var(--el-border-color-lighter);
  font-size: 11px;
  color: var(--el-text-color-secondary);
}

/* Empty */
.ai-panel-empty {
  text-align: center;
  padding: 20px 0;
  color: var(--el-text-color-placeholder);
  font-size: 13px;
}

/* Chart */
.ai-curve-chart {
  width: 100%;
  height: 160px;
}

/* ===== Main Grid ===== */
.arena-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  min-height: 0;
}
.grid-chart, .grid-chat {
  background: var(--panel-bg);
  border: 1px solid var(--panel-border);
  border-radius: var(--panel-radius);
  padding: 16px;
  min-width: 0;
}

/* Panel Header */
.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}
.panel-title {
  font-size: 15px;
  font-weight: 700;
}
.panel-badge {
  background: var(--el-fill-color);
  color: var(--el-text-color-secondary);
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 10px;
}

/* Chart */
.equity-chart {
  width: 100%;
  height: 320px;
}

/* Chat */
.chat-box {
  display: flex;
  flex-direction: column;
  height: 320px;
}
.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 4px 0;
}
.chat-msg {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}
.sys-msg { justify-content: center; }
.user-msg { justify-content: flex-end; }
.user-msg .chat-body { align-items: flex-end; }
.user-msg .chat-content {
  background: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
  border: 1px solid var(--el-color-primary-light-5);
}
.user-msg .chat-name { color: var(--el-color-primary); }
.debate-msg .chat-content {
  background: linear-gradient(135deg, #fff3e0, #fff8e1);
  border: 1px solid #ffcc02;
  position: relative;
}
.debate-msg .chat-content::before {
  content: '⚔';
  position: absolute;
  top: -8px;
  left: -8px;
  font-size: 14px;
}
.event-msg .chat-content {
  background: linear-gradient(135deg, #e8f5e9, #f1f8e9);
  border: 1px solid #81c784;
  font-style: italic;
}
.sys-msg .chat-content {
  color: var(--el-text-color-secondary);
  font-style: italic;
  font-size: 12px;
  background: none;
  padding: 0;
}
.chat-avatar {
  font-size: 20px;
  flex-shrink: 0;
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--el-fill-color-lighter);
  border-radius: 8px;
}
.chat-body { flex: 1; min-width: 0; }
.chat-name {
  font-size: 12px;
  font-weight: 600;
  margin-bottom: 3px;
  color: var(--el-text-color-regular);
}
.chat-content {
  font-size: 13px;
  line-height: 1.6;
  background: var(--el-fill-color-lighter);
  padding: 8px 12px;
  border-radius: 10px;
  border-top-left-radius: 2px;
  white-space: pre-wrap;
  word-break: break-word;
}
.chat-time {
  font-size: 10px;
  color: var(--el-text-color-placeholder);
  margin-top: 3px;
}
.chat-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 40px 0;
  color: var(--el-text-color-placeholder);
  font-size: 13px;
}
.chat-input-wrap {
  border-top: 1px solid var(--panel-border);
  padding-top: 10px;
}

/* ===== Trades Panel ===== */
.trades-panel {
  background: var(--panel-bg);
  border: 1px solid var(--panel-border);
  border-radius: var(--panel-radius);
  padding: 16px;
}
.trades-table { border-radius: 8px; }

/* Leaderboard */
.leaderboard-panel {
  background: var(--panel-bg);
  border: 1px solid var(--panel-border);
  border-radius: var(--panel-radius);
  padding: 16px;
}
.leaderboard-table { border-radius: 8px; }
.rank-badge {
  display: inline-flex; align-items: center; justify-content: center;
  width: 22px; height: 22px; border-radius: 50%;
  font-size: 11px; font-weight: 700;
  background: var(--el-fill-color-light);
  color: var(--el-text-color-secondary);
}
.rank-badge.top {
  background: linear-gradient(135deg, #ffd700, #ffaa00);
  color: #fff;
}
.lb-player { display: flex; align-items: center; gap: 8px; }
.lb-avatar { font-size: 18px; }
.lb-name { font-size: 13px; font-weight: 600; }
.lb-model { font-size: 11px; color: var(--el-text-color-placeholder); }

/* Event Timeline */
.events-panel {
  background: var(--panel-bg);
  border: 1px solid var(--panel-border);
  border-radius: var(--panel-radius);
  padding: 16px;
}
.events-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 320px;
  overflow-y: auto;
}
.event-item {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 8px 12px;
  border-radius: 8px;
  background: var(--el-fill-color-lighter);
  transition: background 0.2s;
}
.event-item:hover { background: var(--el-fill-color-light); }
.event-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--el-color-info);
  margin-top: 5px;
  flex-shrink: 0;
}
.event-item.limit_up .event-dot { background: var(--el-color-danger); }
.event-item.limit_down .event-dot { background: var(--el-color-success); }
.event-item.stop_loss .event-dot { background: var(--el-color-warning); }
.event-item.major_drawdown .event-dot { background: var(--el-color-danger); }
.event-item.rank_change .event-dot { background: var(--el-color-primary); }
.event-content { flex: 1; }
.event-title { font-size: 13px; font-weight: 500; line-height: 1.4; }
.event-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 4px;
  font-size: 11px;
  color: var(--el-text-color-secondary);
}
.event-avatar { font-size: 14px; }
.event-time { font-family: var(--font-mono, monospace); }
.trade-player {
  display: flex;
  align-items: center;
  gap: 6px;
}
.trade-player-name { font-size: 12px; font-weight: 500; }
.trade-time { font-size: 11px; color: var(--el-text-color-secondary); font-family: var(--font-mono, monospace); }
.trade-stock { display: flex; flex-direction: column; }
.trade-symbol { font-weight: 600; font-size: 12px; font-family: var(--font-mono, monospace); }
.trade-name { font-size: 10px; color: var(--el-text-color-placeholder); }
.trade-price, .trade-amount { font-size: 12px; font-family: var(--font-mono, monospace); }
.trade-fee { font-size: 11px; color: var(--el-text-color-placeholder); }

/* Profit / Loss */
.profit { color: #ef232a; }
.loss { color: #14b143; }

/* ===== Curl Section ===== */
.curl-section {
  background: var(--el-fill-color-lighter);
  border: 1px solid var(--panel-border);
  border-radius: 10px;
  padding: 14px;
}
.curl-header {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 10px;
}
.curl-icon { font-size: 16px; }
.curl-title { font-weight: 600; font-size: 13px; }
.curl-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 8px;
}
.curl-msg {
  font-size: 12px;
  padding: 4px 10px;
  border-radius: 6px;
}
.curl-msg.ok { color: #67c23a; background: #f0f9eb; }
.curl-msg.err { color: #f56c6c; background: #fef0f0; }

/* Avatar Picker */
.avatar-picker {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.avatar-selected {
  width: 48px;
  height: 48px;
  font-size: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--el-fill-color-lighter);
  border: 2px solid var(--el-border-color);
  border-radius: 10px;
}
.avatar-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  max-height: 100px;
  overflow-y: auto;
  padding: 6px;
  background: var(--el-fill-color-lighter);
  border-radius: 8px;
}
.avatar-emoji {
  width: 30px;
  height: 30px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
  cursor: pointer;
  border-radius: 6px;
  transition: all 0.15s;
}
.avatar-emoji:hover {
  background: var(--el-border-color-lighter);
  transform: scale(1.15);
}
.avatar-emoji.active {
  background: var(--el-color-primary-light-9);
  outline: 2px solid var(--el-color-primary);
}

@media (max-width: 800px) {
  .arena-grid { grid-template-columns: 1fr; }
  .comp-grid { grid-template-columns: 1fr; }
  .stats-row { grid-template-columns: repeat(2, 1fr); }
  .arena-hero { flex-direction: column; gap: 12px; align-items: flex-start; }
  .arena-hero-right { flex-wrap: wrap; }
}
.model-list {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 6px;
  max-height: 120px;
  overflow-y: auto;
}
.model-tag {
  cursor: pointer;
  transition: all 0.15s;
}
.model-tag:hover {
  opacity: 0.8;
}
</style>
