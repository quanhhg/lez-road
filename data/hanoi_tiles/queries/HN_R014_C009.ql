[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](21.158779,105.676131,21.204155,105.724511)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](21.158779,105.676131,21.204155,105.724511);
  node["barrier"](21.158779,105.676131,21.204155,105.724511);
);
(._; >>;);
out meta;
out count;
