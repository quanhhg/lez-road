[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](20.751772,105.770361,20.797173,105.818634)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](20.751772,105.770361,20.797173,105.818634);
  node["barrier"](20.751772,105.770361,20.797173,105.818634);
);
(._; >>;);
out meta;
out count;
