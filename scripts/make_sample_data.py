"""Generates sample_data/sales.csv (deterministic)."""
import csv
import random
from datetime import date, timedelta

random.seed(7)
products = {"Aurora Lamp": ("Home", 49), "Nimbus Chair": ("Home", 189), "Pulse Earbuds": ("Electronics", 79),
            "Vertex Monitor": ("Electronics", 329), "Trail Backpack": ("Outdoor", 99), "Summit Tent": ("Outdoor", 249),
            "Brew Kettle": ("Kitchen", 59), "Forge Knife Set": ("Kitchen", 139), "Loop Yoga Mat": ("Fitness", 35),
            "Titan Dumbbells": ("Fitness", 119)}
regions, channels = ["North", "South", "East", "West"], ["web", "store", "partner"]
start = date(2025, 1, 1)
with open("sample_data/sales.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["order_id", "order_date", "customer_id", "product", "category", "region", "channel", "quantity", "unit_price", "discount_pct", "revenue"])
    for i in range(1, 1201):
        d = start + timedelta(days=int(random.random() ** 0.8 * 540))
        p = random.choices(list(products), weights=[9, 4, 12, 3, 7, 3, 10, 4, 11, 5])[0]
        cat, price = products[p]
        qty = random.choice([1, 1, 1, 2, 2, 3, 5])
        disc = random.choice([0, 0, 0, 5, 10, 15])
        rev = round(qty * price * (1 - disc / 100), 2)
        w.writerow([i, d.isoformat(), f"C{random.randint(1, 300):04d}", p, cat, random.choice(regions),
                    random.choice(channels), qty, price, disc, "" if random.random() < 0.01 else rev])
