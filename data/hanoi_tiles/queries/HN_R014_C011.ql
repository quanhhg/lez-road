[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](21.158339,105.772445,21.203742,105.820854)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](21.158339,105.772445,21.203742,105.820854);
  node["barrier"](21.158339,105.772445,21.203742,105.820854);
);
(._; >>;);
out meta;
out count;
