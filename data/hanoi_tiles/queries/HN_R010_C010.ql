[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](20.977870,105.723414,21.023258,105.771748)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](20.977870,105.723414,21.023258,105.771748);
  node["barrier"](20.977870,105.723414,21.023258,105.771748);
);
(._; >>;);
out meta;
out count;
