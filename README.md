# Реєстр подань із квитанціями

POST /submissions приймає `group_code` (наприклад, SE-42) і `submission_key`. Ключ унікальний в SQLite. Перше подання повертає 201, повтор із тим самим ключем — 200 і той самий номер. GET /submissions/<id> читає запис. У v2 квитанція формується після транзакції. Навчальний тайм-аут квитанції повертає 503, а /health залишається доступним. Дані експерименту синтетичні.

## Перевірки й артефакти

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-test.txt
python lab.py test --timeout 45
```

Тестовий крок у GitHub Actions викликає ту саму команду. Завдяки pipefail у Bash конвеєр із tee повертає статус помилки тестів. Крок пакування виконується лише за успішних перевірок. У гілці experiment/failing-health-check очікуваний код /health змінено на 204, що зупиняє пакування. Нижче наведено прогони випусків з виправленим контекстом Docker. Образи створено для Linux ARM64.

- [v1.0.1](https://github.com/vitaliibyliuk/receipt-rollout-lab/actions/runs/45606024470)
- [v2.0.1](https://github.com/vitaliibyliuk/receipt-rollout-lab/actions/runs/45606024300)
- [Невдалий тест і пропущене пакування](https://github.com/vitaliibyliuk/receipt-rollout-lab/actions/runs/45605957327)

```bash
gh run download 45606024470 -n image-v1.0.1 -D local-artifacts/v1
gh run download 45606024300 -n image-v2.0.1 -D local-artifacts/v2
```

Копії цих самих файлів доступні в [GitHub Releases](https://github.com/vitaliibyliuk/receipt-rollout-lab/releases). Якщо обидва каталоги вже містять архіви, відразу переходь до доставки. Скрипт перевіряє суму архіву та ID образу перед запуском.

## Пробний запуск на staging

```bash
for version in v1 v2; do
  bash scripts/deliver.sh "local-artifacts/$version" staging
  stage=$(docker compose -p receipt-stage ps -q stage)
  python -m pytest -q --hosts="docker://$stage" infra
  curl -fsSi --max-time 4 -H 'Content-Type: application/json' \
    -d "{\"group_code\":\"SE-42\",\"submission_key\":\"stage-$version-$(date +%s)\"}" \
    http://127.0.0.1:8191/submissions
done
```

Staging використовує власний том. Робочі версії мають спільний том і порти 8181 та 8182. Прапорець `LAB_CANARY_FAIL` увімкни для v2 лише на робочому стенді.

## Три серії та пороги

Оператор релізу дозволяє збільшення трафіку після щонайменше 20 спроб на v2, частки помилок до 5% та p95 до 200 мс. Кожна серія містить 200 спроб, інтервал 25 мс, тайм-аут 2 с. Кенері отримує кожен десятий POST. Частка помилок враховує 5xx та відсутність відповіді. SLI — частка всіх спроб, які повернули 201 не пізніше ніж за 1 с. SLO становить 99%. p95 — найближчий ранг серед завершених відповідей.

Для повтору вкажи нові `prefix` та `output`.

```bash
prefix="receipt-$(date +%s)"
output="results/$prefix"
bash scripts/deliver.sh local-artifacts/v1 working
docker compose -p receipt-work up -d prometheus
python scripts/traffic.py baseline --prefix "$prefix" --output "$output"
LAB_CANARY_FAIL=1 bash scripts/deliver.sh local-artifacts/v2 working
python scripts/traffic.py canary --prefix "$prefix" --output "$output" &
traffic=$!
sleep 2
docker stats --no-stream $(docker compose -p receipt-work ps -q v1 v2)
wait "$traffic"
sleep 2
python scripts/metrics.py --output "$output/canary-prometheus.json"
docker compose -p receipt-work logs --no-log-prefix v1 v2 | awk '/^[{]/' > "$output/canary.jsonl"
```

Якщо пороги порушено, оператор припиняє надсилати запити на v2 й зупиняє її контейнер. Том залишається підключеним до v1.

```bash
docker compose -p receipt-work stop v2
python scripts/traffic.py rollback --prefix "$prefix" --output "$output"
docker compose -p receipt-work logs --no-log-prefix v1 v2 | awk '/^[{]/' > "$output/submissions.jsonl"
python lab.py summarize "$output/submissions.jsonl"
python lab.py summarize "$output/missing.jsonl"
```

У canary.csv візьми submission_id та submission_key з першого рядка v2 зі статусом 503. Прочитай запис через GET на порті 8181 і повтори POST із тим самим ключем і групою SE-42. Після перевірки можна зупинити стенди з командами нижче. Томи SQLite зберігаються.

```bash
docker compose -p receipt-work --profile working down
docker compose -p receipt-stage --profile staging down
```

## Підготовка й перевірка

ШІ допоміг із чернетками Python-коду, конфігурації збірки та звіту. Роботу перевірено прогонами pytest, Testinfra, GitHub Actions і реальними запитами до контейнерів.
