[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](21.203016,105.869021,21.248446,105.917473)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](21.203016,105.869021,21.248446,105.917473);
  node["barrier"](21.203016,105.869021,21.248446,105.917473);
);
(._; >>;);
out meta;
out count;
