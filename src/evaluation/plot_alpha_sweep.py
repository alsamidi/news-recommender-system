import json
import matplotlib.pyplot as plt

d = json.load(open("models/alpha_sweep.json"))
rows = d["rows"]
xs = [r["alpha"] for r in rows]
ndcg = [r["ndcg@10"] for r in rows]
map10 = [r["map@10"] for r in rows]

plt.figure(figsize=(8, 5))
plt.plot(xs, ndcg, marker="o", label="NDCG@10")
plt.plot(xs, map10, marker="s", label="MAP@10")
for x, y in zip(xs, ndcg):
    plt.text(x, y + 0.00012, f"{y:.4f}", ha="center", fontsize=7)
plt.xlabel("alpha (bobot content; 0.0=pure CF, 1.0=pure Content)")
plt.ylabel("skor")
plt.title("Alpha sweep: NDCG@10 + MAP@10 (dev, protokol hybrid)")
plt.xticks(xs)
plt.grid(True, alpha=0.3)
plt.legend()
plt.tight_layout()
plt.savefig("models/alpha_sweep_curve.png", dpi=150)
print("saved models/alpha_sweep_curve.png")
