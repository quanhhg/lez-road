[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](21.068430,105.675721,21.113806,105.724072)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](21.068430,105.675721,21.113806,105.724072);
  node["barrier"](21.068430,105.675721,21.113806,105.724072);
);
(._; >>;);
out meta;
out count;
