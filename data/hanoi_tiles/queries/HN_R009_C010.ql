[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](20.932695,105.723197,20.978084,105.771516)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](20.932695,105.723197,20.978084,105.771516);
  node["barrier"](20.932695,105.723197,20.978084,105.771516);
);
(._; >>;);
out meta;
out count;
