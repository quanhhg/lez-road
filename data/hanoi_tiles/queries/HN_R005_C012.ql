[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](20.751537,105.818387,20.796950,105.866674)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](20.751537,105.818387,20.796950,105.866674);
  node["barrier"](20.751537,105.818387,20.796950,105.866674);
);
(._; >>;);
out meta;
out count;
