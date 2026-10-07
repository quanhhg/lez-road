[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](20.841886,105.818875,20.887300,105.867191)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](20.841886,105.818875,20.887300,105.867191);
  node["barrier"](20.841886,105.818875,20.887300,105.867191);
);
(._; >>;);
out meta;
out count;
