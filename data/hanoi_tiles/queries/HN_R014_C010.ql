[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](21.158566,105.724288,21.203955,105.772683)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](21.158566,105.724288,21.203955,105.772683);
  node["barrier"](21.158566,105.724288,21.203955,105.772683);
);
(._; >>;);
out meta;
out count;
