[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](21.068218,105.723850,21.113607,105.772214)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](21.068218,105.723850,21.113607,105.772214);
  node["barrier"](21.068218,105.723850,21.113607,105.772214);
);
(._; >>;);
out meta;
out count;
