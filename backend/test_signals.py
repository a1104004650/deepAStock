import asyncio
from app.core.datasource.manager import DataSourceManager
from app.db.session import SessionLocal
from app.core.market.intraday_analyzer import analyze_intraday

async def test():
    async with SessionLocal() as db:
        dsm = DataSourceManager(db)
        
        stocks = [
            ('SH600667', '太极实业'),
            ('SZ002134', '天津普林'),
            ('SH601012', '隆基绿能'),
            ('SZ000725', '京东方A'),
        ]
        
        for sym, name in stocks:
            rows = dsm.primary.get_intraday(sym)
            if rows:
                result = analyze_intraday(rows, 0)
                print(f'{name}: {len(result["signals"])} 信号')
                counts = {}
                for s in result['signals']:
                    counts[s['signal']] = counts.get(s['signal'], 0) + 1
                for k, v in counts.items():
                    print(f'  {k}: {v}')

asyncio.run(test())
