---
name: project-kickoff
description: >
  プロジェクト開始時・方向転換時・機能追加時に一問一答インタビューを行い、
  プロジェクト文書と .claude/ 配下の設定ファイル群を自動生成するスキル。
  SessionStartフックで自動起動する。
  「プロジェクト開始」「案件開始」「新規案件」「方向転換」「仕様変更」「機能追加」
  「要件変更」「スコープを変えたい」「計画を見直したい」「何から始めれば」
  「キックオフ」「要件定義して」といった言葉が出たら必ずこのスキルを使うこと。
  セッション開始時に既存の CLAUDE.md が見つからない場合も自動で起動すること。
  Claude Code の運用原則（Plan Mode・自己検証・並列実行・権限設計・hooks強制）を
  プロジェクト開始時点から組み込むことで、手戻りと確認ダイアログ疲れを防ぐ。
---

# Project Kickoff スキル

## 目的

プロジェクト開始・方向転換・機能追加の3つのタイミングで起動し、一問一答インタビューを通じて
プロジェクト文書と Claude Code の動作設定を一括生成する。

Claude Code の実戦運用で効く3原則を開始時点から設計に組み込む。
1. **Plan Mode で調査と実装を分ける**（誤実装と手戻りを減らす）
2. **Claude 自身に検証させる**（テスト・CLI出力の自己チェックを定義する）
3. **並列実行を前提に設計する**（git worktree 3〜5本で待ち時間をなくす）

---

## 生成するファイル構成

```
<project-root>/
├── _INDEX.md                        # MOC（Obsidianホームノート・全ノートへの索引）
├── CLAUDE.md                        # AI指示書（行動方針・ルール・ファイル構成）
│
├── docs/                            # プロジェクト文書（Obsidianで閲覧可）
│   ├── REQUIREMENTS.md              # 要件定義書
│   ├── PROCEDURE.md                 # 手順書
│   └── HOOK.md                      # フック設計書
│
├── memory/                          # AI記憶
│   └── MEMORY.md
│
├── tasks/                           # タスク管理
│   ├── NEXT_TASKS.md
│   ├── todo.md
│   └── lessons.md
│
└── .claude/                         # Claude Code 設定（隠しフォルダ）
    ├── settings.json                # 権限設定（allow/ask/deny）+ フック設定
    │
    ├── skills/                      # 繰り返し作業の手順書（手動トリガー）
    │   └── (インタビュー回答から生成)
    │
    └── agents/                      # 品質チェック自動エージェント（PostToolUse）
        └── (インタビュー回答から生成)
```

### `.claude/skills/` と `.claude/agents/` の違い

| 項目 | `.claude/skills/` | `.claude/agents/` |
|---|---|---|
| 起動方法 | Claude が呼ばれたとき（手動トリガー） | コード生成ツール実行後に自動起動（PostToolUse） |
| 役割 | 「〇〇して」に応えるための手順書 | 品質・安全性・整合性を自動チェックするゲート |
| 例 | `deploy.md`（デプロイ手順）、`create-report.md`（レポート生成） | `security-reviewer.md`（XSS検出）、`seo-checker.md`（SEO検査） |

### CLAUDE.md と hooks の違い（重要）

| 項目 | CLAUDE.md | hooks（settings.json） |
|---|---|---|
| 性質 | **助言**：Claudeへの指示・方針 | **強制**：例外なく自動実行される |
| 更新頻度 | 同じミスを2回したら即追記。不要ルールは削除 | 「絶対に守るべき最小集合」のみ登録する |
| 例 | コーディング規約・命名方針・禁止事項 | prettier自動整形・secretsへの書き込みブロック |

---

## ステップ0：モードを判定する

```powershell
$isNew = (-not (Test-Path "CLAUDE.md")) -and (-not (Test-Path "docs\REQUIREMENTS.md"))
Write-Host $(if ($isNew) { "新規モードで起動します" } else { "変更モードで起動します" })
```

**新規モード**：全問インタビューを実施し、全ファイルを生成する

**変更モード**：既存ファイルを読み込み、「何が変わりましたか？」の1問から開始する。
影響するファイルのみを差分更新する。更新前ファイルは `_archive/YYYY-MM-DD/` に退避する。

---

## ステップ1：一問一答インタビュー（全13問）

**ルール：必ず1問ずつ聞く。各問いには「私の推奨」を添える。**

---

### 問1：プロジェクトの名前と一行説明

```
このプロジェクトに名前をつけてください。
また、一文（30字以内）で「何のためのプロジェクトか」を説明してください。

私の推奨：フォルダ名・ファイル名にも使うため、英数字とハイフンのみの
短い名前（例: ga4-auto-report）にすると扱いやすいです。
```

→ `_INDEX.md`・`CLAUDE.md`・`docs/REQUIREMENTS.md` のヘッダーに埋め込む

---

### 問2：誰のための・何の問題を解決するプロジェクトか

```
誰が・どんな状況で・どんな問題を解決するためのプロジェクトですか？

私の推奨：「担当者がGA4を手動でコピペする月初3時間の作業をなくす」のように
"誰が・何をしなくて済むか" を動詞で表現すると後で要件がブレません。
```

→ `docs/REQUIREMENTS.md` ユーザー文脈セクション

---

### 問3：完成の定義（誰がどうやって確認するか）

```
どうなったら「完成」と言えますか？誰がどうやって確認しますか？

私の推奨：「自分がスクリプトを実行してExcelが出て、数値が手作業と一致したらOK」のように
「誰が・何を見て・何と照合してOKとするか」まで決めておくと手戻りがなくなります。
```

→ `docs/REQUIREMENTS.md` 完了判定・`CLAUDE.md` 完了条件

---

### 問4：スコープ（やること・やらないことを両方）

```
このプロジェクトで「やること」と「やらないこと」を教えてください。
特に「やらないこと」を明確にしてほしいです。

私の推奨：除外を先に決めると後からの追加要求を防げます。
```

→ `docs/REQUIREMENTS.md` スコープセクション

---

### 問5：技術スタック・制約・既存環境

```
使用する技術・言語・ツール・既存システムとの連携はありますか？
動かせない制約があれば教えてください。

私の推奨：「Windows + PowerShell + Python 3.11。GA4はAPIキーあり。
Dockerは使えない」のように環境の輪郭を先に決めておきます。
```

→ `CLAUDE.md` 技術環境・`docs/REQUIREMENTS.md` 技術制約・`docs/PROCEDURE.md` 前提環境

---

### 問6：実装・実行の大まかな流れ

```
ゴールまで進めるとき、どういう順番で進めますか？
「まず→次に→最後に」の形で大きなステップを教えてください。

私の推奨：各ステップに「完了確認方法」をセットにしておくと進捗が見えやすくなります。
また、大きな変更を始めるときは必ず Plan Mode で調査・計画を先に行い、
実装は別セッションで行う運用を推奨します。
```

→ `docs/PROCEDURE.md` 実装フロー

---

### 問7：Claude に出力を検証させるコマンドは何か（自己検証設計）

```
Claude が実装・編集を終えた後、「本当に正しく動いているか」を
Claude 自身に確認させるコマンドやテスト手順はありますか？

例：
  - npm test を実行してすべてパスすることを確認する
  - python -m pytest tests/ を実行してエラーがないことを確認する
  - 画面のスクリーンショットを撮って UI 崩れがないか確認する

私の推奨：「修正後に必ず ○○ を実行し、結果をユーザーに報告してから完了とする」
というルールを CLAUDE.md に書いておくと、人間がレビューする前に Claude 自身が
問題を発見して直してくれるようになります。検証コマンドが重い場合は
スモークテスト（最小限の動作確認）から始めてください。
```

→ `CLAUDE.md` 自己検証ルール・`docs/PROCEDURE.md` 検証フロー

---

### 問8：繰り返し呼び出したい定型作業はあるか（skills）

```
「これを毎日やる」「Claude に頼む作業のパターンがある」というものはありますか？
あれば作業名と、何をするかを教えてください。（例: レポート作成・デプロイ確認・記事投稿）

ない場合は「なし」と答えてください。

私の推奨：1日1回以上やることは .claude/skills/ に手順書として登録しておくと、
「〇〇して」と言うだけで Claude が一定の手順で動くようになります。
使うまでほぼコストはかかりません。
ただし skills が増えすぎると発火タイミングが曖昧になるので、
長い参考資料は分割して管理してください。
```

→ `.claude/skills/{{作業名}}.md` を生成する（1作業1ファイル）

---

### 問9：コードを書いた後に自動でチェックしてほしいことはあるか（agents）

```
コードや成果物が出来上がった後、毎回確認したい品質チェックはありますか？
（例: セキュリティ確認・SEO検査・命名規則チェック・パフォーマンス確認）

ない場合は「なし」と答えてください。

私の推奨：チェック項目をエージェントとして .claude/agents/ に登録すると、
Claude がコードを書き終えるたびに自動でレビューが走るようになります。
ただし hooks は「絶対に守るべき最小集合」のみにしておかないと保守が重くなります。
```

→ `.claude/agents/{{チェック名}}.md` を生成する（1チェック1ファイル）
→ `docs/HOOK.md` の PostToolUse 設定に自動反映する

---

### 問10：SessionStart で自動実行したいことはあるか（hooks）

```
プロジェクトを開いたとき（セッション開始時）に、
自動でやってほしいことはありますか？

私の推奨：「前回のタスクを表示する」「アップデートを確認する」が典型的な使い方です。
設定しない場合は「なし」と答えてください。
```

→ `docs/HOOK.md` SessionStart 設定・`.claude/settings.json`

---

### 問11：権限設計（allow / ask / deny の仕分け）

```
Claude に「自動でやっていい操作」「毎回確認が必要な操作」「絶対にやってはいけない操作」を
教えてください。

例：
  自動でOK（allow）: npm test の実行、ファイル編集
  確認が必要（ask） : git push
  絶対NG（deny）   : .env ファイルの読み取り、secrets/ 配下の書き込み

私の推奨：.env・secrets 系は必ず deny にしてください。
allow を広げすぎると誤操作リスクが上がります。
設定はルートから順に deny → ask → allow の順に評価されます。
```

→ `.claude/settings.json` の permissions セクション

---

### 問12：Claudeへの制約・禁止事項・行動方針

```
Claudeに守ってほしいルールや、やってほしくない行動はありますか？

私の推奨：「関数は20行以内・テストなしのコードはコミット禁止・
エラー時は原因・影響・対応の3点を必ず報告」のようなルールが
後の実装品質を左右します。

また、同じミスを2回したら必ず CLAUDE.md に追記してください。
逆に使わなくなったルールは削除してください。
CLAUDE.md は「現在有効なルール集」として簡潔に保つことが重要です。
```

→ `CLAUDE.md` 行動ルールセクション

---

### 問13：今すぐ着手するタスク（3〜5件）

```
インタビューが終わったら最初に何をしますか？
「今日→次にやること→今週中」の3段階で3〜5件のタスクを教えてください。

私の推奨：最初のタスクは「環境が動くか確認する」にすることを勧めます。
大きな変更は必ず Plan Mode での調査から始めてください。
```

→ `tasks/NEXT_TASKS.md`

---

## ステップ2：矛盾チェック

13問の回答を横断して以下を確認する。矛盾があればユーザーに確認してから生成に進む。

- 期限とスコープが合わない
- 技術制約と成果物の形式が矛盾する
- agents に登録したチェックが技術スタック上で実現できない
- deny に設定した操作が自己検証コマンドと矛盾する

---

## ステップ3：ファイルを生成する

テンプレートは `references/` を参照すること。

```powershell
$root = Get-Location

# フォルダを作成する
foreach ($dir in @("docs","memory","tasks",".claude\skills",".claude\agents")) {
    New-Item -ItemType Directory -Force -Path "$root\$dir" | Out-Null
}

# 既存ファイルはスキップする関数
function Write-IfNotExist($relPath, $content) {
    $path = Join-Path $root $relPath
    if (Test-Path $path) {
        Write-Host "スキップ（既存）: $relPath"
    } else {
        $dir = Split-Path $path -Parent
        if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
        Set-Content -Path $path -Value $content -Encoding UTF8
        Write-Host "作成: $relPath"
    }
}
```

### 生成ファイル一覧

| ファイル | テンプレート | 新規 | 変更モード |
|---|---|---|---|
| `_INDEX.md` | `references/_INDEX.md.tmpl` | 生成 | `docs/`セクションを追記 |
| `CLAUDE.md` | `references/CLAUDE.md.tmpl` | 生成 | スキップ |
| `docs/REQUIREMENTS.md` | `references/REQUIREMENTS.md.tmpl` | 生成 | アーカイブ後に再生成 |
| `docs/PROCEDURE.md` | `references/PROCEDURE.md.tmpl` | 生成 | アーカイブ後に再生成 |
| `docs/HOOK.md` | `references/HOOK.md.tmpl` | 生成 | アーカイブ後に再生成 |
| `memory/MEMORY.md` | create-directory の tmpl を流用 | 生成 | スキップ |
| `tasks/NEXT_TASKS.md` | `references/NEXT_TASKS.md.tmpl` | 生成 | 再生成 |
| `tasks/todo.md` | create-directory の tmpl を流用 | 生成 | スキップ |
| `tasks/lessons.md` | create-directory の tmpl を流用 | 生成 | スキップ |
| `.claude/settings.json` | `references/settings.json.tmpl` | 生成 | フック・権限セクションのみ追記 |
| `.claude/skills/{{name}}.md` | `references/skill-stub.md.tmpl` | 問8の回答数だけ生成 | 差分追加 |
| `.claude/agents/{{name}}.md` | `references/agent-stub.md.tmpl` | 問9の回答数だけ生成 | 差分追加 |

---

### `.claude/settings.json` の権限セクション雛形

問11の回答をもとに以下の形式で生成する。

```powershell
# settings.json の権限セクション確認
Get-Content ".claude\settings.json" | ConvertFrom-Json | Select-Object -ExpandProperty permissions
```

```json
{
  "permissions": {
    "allow": ["Bash(npm test *)", "Bash(python -m pytest *)"],
    "ask":   ["Bash(git push *)"],
    "deny":  ["Read(./.env)", "Read(./secrets/**)","Write(./secrets/**)"]
  }
}
```

**評価順序：deny → ask → allow の順に評価される。**
deny に該当しなければ ask、ask にも該当しなければ allow の判定に進む。

---

### `CLAUDE.md` の自己検証ルール雛形

問7の回答をもとに以下を CLAUDE.md の「行動ルール」セクションに追記する。

```markdown
## 自己検証ルール

- 実装・編集を終えたら、必ず以下のコマンドを実行し、結果をユーザーに報告してから完了とする。
  - {{問7で指定されたコマンド}}
- 検証が通らない場合は、修正してから再度実行する。人間に引き渡す前に自己完結させること。

## CLAUDE.md の更新ルール

- 同じミスを2回犯したら、その禁止事項をこのファイルに追記すること。
- 使わなくなったルールは削除すること。CLAUDE.md は常に「今有効なルールだけ」を保つ。
```

---

## ステップ4：_INDEX.md の更新（変更モード時）

変更モードで `_INDEX.md` が既存の場合、`docs/` セクションが欠けていれば追記する。

```powershell
$indexPath = Join-Path $root "_INDEX.md"
$docsSection = "## プロジェクト文書"

if ((Test-Path $indexPath) -and ((Get-Content $indexPath -Raw) -notmatch [regex]::Escape($docsSection))) {
    $append = @"

## プロジェクト文書

- [[docs/REQUIREMENTS]] — 要件定義書
- [[docs/PROCEDURE]] — 手順書
- [[docs/HOOK]] — フック設計書
"@
    Add-Content -Path $indexPath -Value $append -Encoding UTF8
    Write-Host "追記: _INDEX.md に docs/ セクションを追加"
}
```

---

## ステップ5：完了報告

```
=== Project Kickoff 完了 ===

生成したファイル：
  ✅ _INDEX.md
  ✅ CLAUDE.md（自己検証ルール・CLAUDE.md更新ルール含む）
  ✅ docs/REQUIREMENTS.md
  ✅ docs/PROCEDURE.md
  ✅ docs/HOOK.md
  ✅ memory/MEMORY.md
  ✅ tasks/NEXT_TASKS.md
  ✅ tasks/todo.md
  ✅ tasks/lessons.md
  ✅ .claude/settings.json（権限設計 allow/ask/deny 含む）
  ✅ .claude/skills/{{問8で登録した作業名}}.md  （×件）
  ✅ .claude/agents/{{問9で登録したチェック名}}.md （×件）

Claude Code 運用の3原則（初回セッションから意識してください）：
  1. 大きな変更は必ず Plan Mode で調査→計画してから実装に入る
  2. 実装後は必ず自己検証コマンドを実行し、人間に引き渡す前に自己完結させる
  3. 同じミスを2回したら即 CLAUDE.md に追記する

次の一手：
  1. _INDEX.md を Obsidian でピン留めしてホームページにする
  2. docs/HOOK.md の手順に従って settings.json のフックを確認する
  3. tasks/NEXT_TASKS.md の最初のタスクに着手する（最初は Plan Mode から）

方向転換・機能追加が生じた場合は「方向転換」と伝えるだけで再起動します。
```

---

## 変更モードの動作

**変更-1**：「何が変わりましたか？」の1問から開始する

**変更-2**：影響するファイルを特定して提示する

```
影響するファイル：
  docs/REQUIREMENTS.md → スコープセクションを更新
  docs/HOOK.md         → 新しいエージェントを追加
  .claude/agents/      → seo-checker.md を新規追加
  .claude/settings.json → permissions の deny を追加
  tasks/NEXT_TASKS.md  → 全面更新
```

**変更-3**：影響箇所に必要な情報だけを追加で確認し、差分更新する

---

## 注意事項

- 問6（手順）・問7（自己検証）・問13（タスク）は「もういい」と言われても省略しない。
- 既存ファイルの更新は必ずアーカイブ後に行う。
- `.claude/agents/` のファイルは `docs/HOOK.md` の PostToolUse 設定と必ず対応させる。エージェントを追加したら HOOK.md も更新すること。
- `.claude/settings.json` の deny リストには `.env` と `secrets/` 配下を必ず含める。
- CLAUDE.md は助言、hooks は強制。この2つを混同しないこと。
- `.claude/` フォルダは Obsidian の除外設定を推奨する（設定 → ファイルとリンク → 除外するファイルに `.claude` を追加）。
- `docs/` フォルダの各ファイルは Obsidian から直接閲覧・編集できる。
