const TIMEZONE = 'Asia/Tokyo';
const WORKFLOW_FILE = 'threads-daily.yml';
const TEST_WORKFLOW_FILE = 'gas-connection-test.yml';
const BRANCH = 'main';
const MANAGEMENT_SHEET_ID =
  '1l4pTd8mbBiEkbnlA7xF2nrvR5OpF_Rv8si3IUqNo3Ak';

// 現在の管理シート：1～3行目はタイトル・説明、4行目が見出し。
const HEADER_ROW = 4;
const DATA_START_ROW = 5;

// 現在の管理シートに実在する8列だけを使用する。
const HEADERS = [
  '予定日時',
  '投稿枠',
  '起動キー',
  '起動状態',
  'GitHub受付',
  'Workflow Run',
  '投稿結果',
  '更新日時',
];

const SLOT_BY_HOUR = {
  7: 'morning',
  12: 'noon',
  20: 'evening',
};

const SLOT_LABEL = {
  morning: '朝 7:00',
  noon: '昼 12:00',
  evening: '夜 20:00',
};

/**
 * 本番用。
 * 1分おきの時間主導型トリガーから呼び出す。
 */
function checkAndDispatch() {
  const now = new Date();
  const date = Utilities.formatDate(now, TIMEZONE, 'yyyy-MM-dd');
  const hour = Number(Utilities.formatDate(now, TIMEZONE, 'H'));
  const minute = Number(Utilities.formatDate(now, TIMEZONE, 'm'));
  const slot = SLOT_BY_HOUR[hour];

  // 7時・12時・20時の0～14分だけ受け付ける。
  // 過ぎた投稿枠は後追いしない。
  if (!slot || minute > 14) return;

  dispatchOnce_(date, slot);
}

/**
 * 同じ日・同じ投稿枠を1回だけ起動する。
 */
function dispatchOnce_(date, slot) {
  const properties = PropertiesService.getScriptProperties();
  const lock = LockService.getScriptLock();
  lock.waitLock(20000);

  const dispatchKey = `${date}-${slot}`;
  const propertyKey = `DISPATCHED_${date}_${slot}`;

  try {
    if (properties.getProperty(propertyKey)) {
      updateManagementRow_(date, slot, dispatchKey, {
        state: '重複停止',
        github: '送信せず',
        workflowRun: '',
        result: '同じ枠は起動済み',
      });
      return;
    }

    updateManagementRow_(date, slot, dispatchKey, {
      state: '起動中',
      github: '送信中',
      workflowRun: '実行待ち',
      result: 'GitHub受付待ち',
    });

    const response = callGitHubWorkflow_(
      properties,
      WORKFLOW_FILE,
      {
        operation: 'dispatch',
        slot: slot,
        target_date: date,
      }
    );

    const status = response.getResponseCode();
    const body = response.getContentText();

    if (status !== 204) {
      updateManagementRow_(date, slot, dispatchKey, {
        state: '失敗',
        github: `HTTP ${status}`,
        workflowRun: '起動失敗',
        result: shortenText_(
          body || 'GitHubからエラー本文が返りませんでした',
          500
        ),
      });
      throw new Error(
        `GitHub dispatch failed: status=${status}, body=${body}`
      );
    }

    // GitHubが受け付けた直後に保存し、二重送信を防ぐ。
    properties.setProperty(propertyKey, new Date().toISOString());

    updateManagementRow_(date, slot, dispatchKey, {
      state: '起動済み',
      github: '204 Accepted',
      workflowRun: 'GitHub Actionsで確認',
      result: 'Workflow実行待ち',
    });
  } catch (error) {
    try {
      updateManagementRow_(date, slot, dispatchKey, {
        state: '失敗',
        github: 'エラー',
        workflowRun: '要確認',
        result: shortenText_(getErrorMessage_(error), 500),
      });
    } catch (sheetError) {
      console.error(
        `Management sheet update failed: ${getErrorMessage_(sheetError)}`
      );
    }
    throw error;
  } finally {
    lock.releaseLock();
  }
}

/**
 * GitHub ActionsのWorkflowを起動する。
 */
function callGitHubWorkflow_(properties, workflowFile, inputs) {
  const owner = requiredProperty_(properties, 'GITHUB_OWNER');
  const repo = requiredProperty_(properties, 'GITHUB_REPO');
  const token = requiredProperty_(properties, 'GITHUB_TOKEN');
  const url =
    `https://api.github.com/repos/` +
    `${encodeURIComponent(owner)}/` +
    `${encodeURIComponent(repo)}/` +
    `actions/workflows/` +
    `${encodeURIComponent(workflowFile)}/dispatches`;

  return UrlFetchApp.fetch(url, {
    method: 'post',
    contentType: 'application/json',
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: 'application/vnd.github+json',
      'X-GitHub-Api-Version': '2022-11-28',
    },
    payload: JSON.stringify({
      ref: BRANCH,
      inputs: inputs,
    }),
    muteHttpExceptions: true,
  });
}

/**
 * GAS→GitHub接続テスト専用。
 * Threads投稿・投稿データ・画像には触れない。
 */
function testDispatchEvening() {
  const date = Utilities.formatDate(
    new Date(),
    TIMEZONE,
    'yyyy-MM-dd'
  );
  const testKey = `TEST-${date}-${Date.now()}`;
  const properties = PropertiesService.getScriptProperties();

  updateManagementRow_(date, 'evening', testKey, {
    state: 'テスト起動中',
    github: '送信中',
    workflowRun: '接続確認待ち',
    result: 'GitHub受付待ち',
  });

  try {
    const response = callGitHubWorkflow_(
      properties,
      TEST_WORKFLOW_FILE,
      { test_label: testKey }
    );
    const status = response.getResponseCode();
    const body = response.getContentText();

    if (status !== 204) {
      updateManagementRow_(date, 'evening', testKey, {
        state: '失敗',
        github: `HTTP ${status}`,
        workflowRun: '起動失敗',
        result: shortenText_(
          body || 'GitHubからエラー本文が返りませんでした',
          500
        ),
      });
      throw new Error(
        `GitHub test dispatch failed: status=${status}, body=${body}`
      );
    }

    updateManagementRow_(date, 'evening', testKey, {
      state: 'テスト起動済み',
      github: '204 Accepted',
      workflowRun: 'GitHub Actionsで確認',
      result: '接続テストWorkflow起動済み',
    });
  } catch (error) {
    updateManagementRow_(date, 'evening', testKey, {
      state: '失敗',
      github: 'エラー',
      workflowRun: '要確認',
      result: shortenText_(getErrorMessage_(error), 500),
    });
    throw error;
  }
}

function updateManagementRow_(date, slot, dispatchKey, values) {
  const sheet = getManagementSheet_();
  const headerMap = getHeaderMap_(sheet);
  const row = findOrCreateRow_(
    sheet,
    headerMap,
    date,
    slot,
    dispatchKey
  );
  const nowText = Utilities.formatDate(
    new Date(),
    TIMEZONE,
    'yyyy-MM-dd HH:mm:ss'
  );

  setCell_(sheet, row, headerMap, '起動キー', dispatchKey);
  setCell_(sheet, row, headerMap, '起動状態', values.state || '');
  setCell_(sheet, row, headerMap, 'GitHub受付', values.github || '');
  setCell_(
    sheet,
    row,
    headerMap,
    'Workflow Run',
    values.workflowRun || ''
  );
  setCell_(sheet, row, headerMap, '投稿結果', values.result || '');
  setCell_(sheet, row, headerMap, '更新日時', nowText);
}

function getManagementSheet_() {
  const spreadsheet = SpreadsheetApp.openById(MANAGEMENT_SHEET_ID);
  const sheets = spreadsheet.getSheets();
  if (!sheets.length) {
    throw new Error('管理シートにタブがありません');
  }
  return sheets[0];
}

function getHeaderMap_(sheet) {
  const lastColumn = sheet.getLastColumn();
  if (lastColumn < 1) {
    throw new Error('管理シートに列がありません');
  }

  const current = sheet
    .getRange(HEADER_ROW, 1, 1, lastColumn)
    .getDisplayValues()[0];
  const map = {};

  current.forEach((value, index) => {
    const header = String(value || '').trim();
    if (header) map[header] = index + 1;
  });

  const missing = HEADERS.filter((header) => !map[header]);
  if (missing.length) {
    throw new Error(
      `管理シート${HEADER_ROW}行目の列が不足しています: ` +
      `${missing.join(', ')}`
    );
  }
  return map;
}

function findOrCreateRow_(
  sheet,
  headerMap,
  date,
  slot,
  dispatchKey
) {
  const lastRow = sheet.getLastRow();

  if (lastRow >= DATA_START_ROW) {
    const dataRowCount = lastRow - DATA_START_ROW + 1;
    const keys = sheet
      .getRange(
        DATA_START_ROW,
        headerMap['起動キー'],
        dataRowCount,
        1
      )
      .getDisplayValues();
    const exactIndex = keys.findIndex(
      (row) => String(row[0] || '').trim() === dispatchKey
    );
    if (exactIndex >= 0) {
      return DATA_START_ROW + exactIndex;
    }

    // テストは既存の投稿予定行を上書きしない。
    if (!dispatchKey.startsWith('TEST-')) {
      const plannedTimes = sheet
        .getRange(
          DATA_START_ROW,
          headerMap['予定日時'],
          dataRowCount,
          1
        )
        .getDisplayValues();
      const slots = sheet
        .getRange(
          DATA_START_ROW,
          headerMap['投稿枠'],
          dataRowCount,
          1
        )
        .getDisplayValues();
      const targetSlotLabel = SLOT_LABEL[slot];
      const plannedIndex = plannedTimes.findIndex((row, index) => {
        const rowDate = extractDate_(row[0]);
        const rowSlot = String(slots[index][0] || '').trim();
        return (
          rowDate === date &&
          (rowSlot === slot || rowSlot === targetSlotLabel)
        );
      });
      if (plannedIndex >= 0) {
        return DATA_START_ROW + plannedIndex;
      }
    }
  }

  const newRow = Math.max(lastRow + 1, DATA_START_ROW);
  const hour = Object.keys(SLOT_BY_HOUR).find(
    (key) => SLOT_BY_HOUR[key] === slot
  );
  const plannedTime = hour
    ? `${date} ${String(hour).padStart(2, '0')}:00`
    : date;

  setCell_(sheet, newRow, headerMap, '予定日時', plannedTime);
  setCell_(
    sheet,
    newRow,
    headerMap,
    '投稿枠',
    SLOT_LABEL[slot] || slot
  );
  setCell_(sheet, newRow, headerMap, '起動キー', dispatchKey);
  return newRow;
}

function extractDate_(value) {
  const text = String(value || '').trim();
  const match = text.match(
    /(\d{4})[\/-](\d{1,2})[\/-](\d{1,2})/
  );
  if (!match) return '';
  return (
    `${match[1]}-` +
    `${match[2].padStart(2, '0')}-` +
    `${match[3].padStart(2, '0')}`
  );
}

function setCell_(sheet, row, headerMap, header, value) {
  const column = headerMap[header];
  if (!column) {
    throw new Error(`管理シートに「${header}」列がありません`);
  }
  sheet.getRange(row, column).setValue(value);
}

function requiredProperty_(properties, name) {
  const value = properties.getProperty(name);
  if (!value) {
    throw new Error(`Script Property ${name} is missing`);
  }
  return value;
}

function getErrorMessage_(error) {
  if (error && typeof error === 'object' && error.message) {
    return String(error.message);
  }
  return String(error);
}

function shortenText_(value, maxLength) {
  const text = String(value || '');
  if (text.length <= maxLength) return text;
  return text.slice(0, maxLength) + '…';
}

/**
 * 誤って保存された本番用重複防止キーを手動解除する内部関数。
 */
function clearTodayDispatchKey_(slot) {
  if (!SLOT_LABEL[slot]) {
    throw new Error(
      'slotは morning / noon / evening のいずれかです'
    );
  }
  const date = Utilities.formatDate(
    new Date(),
    TIMEZONE,
    'yyyy-MM-dd'
  );
  PropertiesService.getScriptProperties().deleteProperty(
    `DISPATCHED_${date}_${slot}`
  );
}
