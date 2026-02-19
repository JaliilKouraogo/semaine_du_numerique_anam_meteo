import { Accordion } from "../components/Accordion";
import { Layout } from "../components/Layout";

const pipelineSteps = [
   {
      icon: "database",
      title: "Collecte de données",
      description:
         "Collecte des données météorologiques nationales et internationales pour constituer un jeu robuste et représentatif.",
   },
   {
      icon: "cleaning_services",
      title: "Nettoyage et prétraitement",
      description: "Nettoyage des valeurs manquantes, harmonisation des unités et préparation aux étapes suivantes.",
   },
   {
      icon: "engineering",
      title: "Ingénierie des caractéristiques",
      description: "Extraction et création d’attributs pertinents pour améliorer la performance des modèles.",
   },
   {
      icon: "model_training",
      title: "Entraînement et évaluation des modèles",
      description: "Entraînement continu des modèles et suivi des métriques clés pour garantir la fiabilité.",
   },
   {
      icon: "monitoring",
      title: "Visualisation et reporting",
      description: "Restitution claire des prévisions et indicateurs via un tableau de bord interactif.",
   },
];


export function AboutPage() {
   return (
      <Layout title="A propos">
         <div className="mx-auto max-w-4xl px-4 sm:px-6 lg:px-8 py-12 md:py-20">
            <header className="text-center mb-16">
               <h1 className="text-4xl md:text-5xl font-black tracking-tighter text-ink ">
                  À propos du projet ANAM-MÉTÉO-EVAL
               </h1>
               <p className="mt-4 max-w-3xl mx-auto text-lg text-muted">
                  Visualisation des données météorologiques et évaluation des performances de prédiction pour le Hackathon
                  MTDPCE 2025.
               </p>
            </header>
            <section className="space-y-16">
               <article>
                  <h2 className="text-2xl font-bold leading-tight tracking-tight text-primary border-b border-[var(--border)] pb-3 mb-6">
                     Vue d'ensemble du projet
                  </h2>
                  <p className="text-base leading-relaxed text-muted">
                     Notre objectif est de proposer un système robuste pour visualiser les données météorologiques et évaluer
                     avec précision les performances des modèles prédictifs dédiés au Burkina Faso.
                  </p>
               </article>
               <article>
                  <h2 className="text-2xl font-bold leading-tight tracking-tight text-primary border-b border-[var(--border)] pb-3 mb-8">
                     Le pipeline de données
                  </h2>
                  <Accordion items={pipelineSteps} />
               </article>
               <article>
                  <h2 className="text-2xl font-bold leading-tight tracking-tight text-primary border-b border-[var(--border)] pb-3 mb-6">
                     Hackathon MTDPCE 2025
                  </h2>
                  <p className="text-base leading-relaxed text-muted">
                     L’initiative MTDPCE mobilise les talents pour résoudre les défis nationaux, notamment en météorologie,
                     afin d’accélérer la transition numérique du Burkina Faso.
                  </p>

               </article>
            </section>
         </div>
      </Layout>
   );
}

